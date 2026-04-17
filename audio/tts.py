"""
audio/tts.py
-------------
Text-to-Speech module for reading Chinese text aloud.

Architecture
------------
One long-lived background thread owns the COM apartment for its entire
lifetime.  A fresh SAPI5 SpVoice COM object is created for EVERY utterance.
This is the only reliable way to avoid SAPI5's silent-failure bug on Windows,
where engine.runAndWait() returns OK but subsequent say() calls produce no
audio.

pyttsx3 is NOT used because it caches the engine as a singleton — repeated
pyttsx3.init() calls return the same broken object, so "recycling" via
pyttsx3 does not actually help.

Key notes
---------
* speak_async() flushes any pending items before enqueueing new text.
* A fresh win32com SpVoice is created per utterance (cheap, thread-safe).
* Falls back to a pyttsx3-subprocess approach if win32com is unavailable.
"""

import threading
import queue

# SAPI5 rate mapping: pyttsx3 wpm → SAPI5 (-10 … 10)
# 130 wpm ≈ -2, 200 wpm ≈ 0
_WPM_TO_SAPI = lambda wpm: max(-10, min(10, (wpm - 200) // 15))  # noqa: E731


class TTSEngine:
    """
    Thread-safe Text-to-Speech wrapper using SAPI5 COM directly.

    Public API
    ----------
    speak_async(text)  – non-blocking playback (preferred for UI code)
    speak(text)        – blocking playback (waits until audio finishes)
    set_rate(wpm)      – change speech rate (words-per-minute, e.g. 130)
    shutdown()         – cleanly stop the background thread
    """

    def __init__(self) -> None:
        self._sapi_rate: int = _WPM_TO_SAPI(130)  # default ≈ slow-ish
        self._voices: list = []
        self.q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="TTS-Worker"
        )
        self._thread.start()

    # ──────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────

    def speak_async(self, text: str) -> None:
        """Non-blocking: discard pending items, then enqueue *text*."""
        print(f"[TTS] speak_async called: '{text}'")
        self._flush_pending()
        self.q.put(text)
        print(f"[TTS] Item enqueued, queue size: {self.q.qsize()}")

    def speak(self, text: str) -> None:
        """Blocking: discard pending items, enqueue *text*, wait for done."""
        self._flush_pending()
        self.q.put(text)
        self.q.join()

    def set_rate(self, wpm: int) -> None:
        """Change speech rate (words-per-minute)."""
        self._sapi_rate = _WPM_TO_SAPI(wpm)

    def get_available_voices(self) -> list:
        return list(self._voices)

    def shutdown(self) -> None:
        """Signal the worker thread to exit cleanly."""
        self.q.put(None)

    # ──────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────

    def _flush_pending(self) -> None:
        """Drain all items not yet picked up by the worker."""
        while not self.q.empty():
            try:
                self.q.get_nowait()
                self.q.task_done()
            except queue.Empty:
                break

    # ── Primary worker: direct SAPI5 via win32com ──────────────────

    def _worker(self) -> None:
        """
        Long-lived background thread.

        Uses win32com.client to call SAPI5 directly.  A brand-new SpVoice
        COM object is created for every utterance, which guarantees clean
        state and reliable audio on every play.
        """
        com_ok = False
        try:
            import pythoncom  # type: ignore
            pythoncom.CoInitialize()
            com_ok = True
        except Exception:
            pass  # non-Windows or pywin32 not installed

        try:
            import win32com.client  # type: ignore

            # ── Locate a Chinese voice token once ────────────────────
            chinese_token = None
            try:
                cat = win32com.client.Dispatch("SAPI.SpObjectTokenCategory")
                cat.SetId(
                    r"HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Speech\Voices",
                    False,
                )
                tokens = cat.EnumerateTokens()
                all_voices = []
                for i in range(tokens.Count):
                    tok = tokens.Item(i)
                    try:
                        desc = tok.GetDescription()
                        tok_id: str = getattr(tok, "Id", "") or ""
                        all_voices.append(desc)
                        if any(
                            kw in desc.lower() or kw in tok_id.lower()
                            for kw in ["zh", "chinese", "mandarin",
                                       "huihui", "yaoyao"]
                        ):
                            chinese_token = tok
                            print(f"[TTS] Chinese voice found: {desc}")
                            break
                    except Exception:
                        continue
                self._voices = all_voices
                if not chinese_token:
                    print("[TTS] Warning: No Chinese voice found – using default.")
            except Exception as ve:
                print(f"[TTS] Voice enumeration failed: {ve}")

            # ── Main loop ────────────────────────────────────────────
            print("[TTS] Waiting for item …")
            while True:
                item = self.q.get()

                # Shutdown sentinel
                if item is None:
                    self.q.task_done()
                    break

                # Rate-change command
                if isinstance(item, tuple) and item[0] == "RATE":
                    self._sapi_rate = _WPM_TO_SAPI(item[1])
                    self.q.task_done()
                    continue

                text: str = item  # type: ignore[assignment]
                print(f"[TTS] Got item: '{text}'")

                try:
                    print(f"[TTS] Speaking: '{text}'")
                    # Create FRESH SpVoice every time — this is the KEY fix.
                    # pyttsx3 caches the engine; we work around that by going
                    # straight to COM and instantiating a new object per call.
                    speaker = win32com.client.Dispatch("SAPI.SpVoice")
                    if chinese_token is not None:
                        speaker.Voice = chinese_token
                    speaker.Rate = self._sapi_rate
                    speaker.Volume = 100
                    speaker.Speak(text)
                    print("[TTS] Speak() returned OK")
                except Exception as exc:
                    print(f"[TTS] Speak error: {exc}")
                finally:
                    self.q.task_done()
                    print("[TTS] task_done() called")

                print("[TTS] Waiting for item …")

        except ImportError:
            # win32com not available → fall back to subprocess-per-utterance
            print("[TTS] win32com unavailable – using subprocess fallback")
            self._worker_subprocess()
        finally:
            if com_ok:
                try:
                    import pythoncom  # type: ignore
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    # ── Fallback worker: subprocess (always fresh process = clean state) ──

    def _worker_subprocess(self) -> None:
        """
        Fallback: each utterance runs in a fresh Python subprocess.
        Immune to all state-corruption issues; slightly slower (~300 ms).
        """
        import subprocess
        import sys

        print("[TTS] Waiting for item …")
        while True:
            item = self.q.get()
            if item is None:
                self.q.task_done()
                break
            if isinstance(item, tuple):
                self.q.task_done()
                continue

            text = str(item)
            print(f"[TTS] Got item (subprocess): '{text}'")
            script = (
                "import pyttsx3; e = pyttsx3.init(); "
                "e.setProperty('rate', 130); e.setProperty('volume', 1.0); "
                f"e.say({repr(text)}); e.runAndWait()"
            )
            try:
                subprocess.run(
                    [sys.executable, "-c", script],
                    timeout=15,
                    capture_output=True,
                )
                print("[TTS] Subprocess speak OK")
            except Exception as exc:
                print(f"[TTS] Subprocess speak failed: {exc}")
            finally:
                self.q.task_done()
                print("[TTS] task_done() called")

            print("[TTS] Waiting for item …")
