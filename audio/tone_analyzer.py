"""
audio/tone_analyzer.py
-----------------------
Analyzes user audio to detect Mandarin tones using pitch (F0) contour analysis via librosa.

Mandarin Tone Patterns:
  Tone 1 (阴平): High and flat     → pitch stays high and even
  Tone 2 (阳平): Rising            → pitch rises from mid to high
  Tone 3 (上声): Falling-Rising    → pitch dips then rises
  Tone 4 (去声): Falling           → pitch sharply drops from high to low
  Tone 5 (轻声): Neutral / Short   → brief, unstressed, low pitch
"""

import numpy as np
import librosa
import sounddevice as sd  # type: ignore
from scipy.io import wavfile


class ToneAnalyzer:
    """
    Records audio from the microphone and analyzes the pitch contour
    to classify the Mandarin tone spoken by the user.
    """

    # Sampling rate for audio recording
    SAMPLE_RATE = 22050
    # Duration in seconds to record user audio
    RECORD_DURATION = 2.0

    def __init__(self):
        self.last_recording = None  # Numpy array of last recorded audio
        self.last_f0 = None         # Pitch (F0) array from last analysis

    def record_audio(self) -> np.ndarray:
        """
        Records audio from the default microphone for RECORD_DURATION seconds.
        Returns a numpy float32 array of the mono audio signal.
        """
        print(f"[ToneAnalyzer] Recording for {self.RECORD_DURATION}s...")
        try:
            # Explicitly query default device to get max input channels
            dev_info = sd.query_devices(sd.default.device[0], 'input')
            channels = min(2, dev_info.get('max_input_channels', 1))
            if channels < 1:
                channels = 1

            audio = sd.rec(
                int(self.RECORD_DURATION * self.SAMPLE_RATE),
                samplerate=self.SAMPLE_RATE,
                channels=channels,
                dtype='float32'
            )
            sd.wait()  # Wait until recording is finished

            # Downmix stereo to mono if needed
            if audio.ndim == 2 and audio.shape[1] > 1:
                audio = audio.mean(axis=1)
            else:
                audio = audio.flatten()

            self.last_recording = audio
            print("[ToneAnalyzer] Recording complete.")
            return audio
        except Exception as e:
            print(f"[ToneAnalyzer] Microphone error: {e}")
            # Return silence on error so the app doesn't crash
            return np.zeros(int(self.RECORD_DURATION * self.SAMPLE_RATE), dtype='float32')

    def record_to_wav(self, wav_path: str) -> str:
        """
        Records audio and saves it as a WAV file.

        - Uses 16-bit PCM mono WAV for broad player compatibility.
        - Returns the same wav_path for convenience.
        """
        audio = self.record_audio()

        # Convert float32 (-1..1) to int16 PCM
        audio_i16 = np.clip(audio, -1.0, 1.0)
        audio_i16 = (audio_i16 * 32767.0).astype(np.int16)

        wavfile.write(wav_path, self.SAMPLE_RATE, audio_i16)
        return wav_path

    def save_last_recording_to_wav(self, wav_path: str) -> str:
        """
        Saves the most recent microphone recording (from record_audio)
        into a WAV file.

        Raises ValueError if no recording exists yet.
        """
        if self.last_recording is None:
            raise ValueError("No previous recording available.")

        audio = self.last_recording
        audio_i16 = np.clip(audio, -1.0, 1.0)
        audio_i16 = (audio_i16 * 32767.0).astype(np.int16)
        wavfile.write(wav_path, self.SAMPLE_RATE, audio_i16)
        return wav_path

    def extract_f0(self, audio: np.ndarray) -> np.ndarray:
        """
        Extracts the fundamental frequency (F0) contour from the audio signal.
        Uses librosa's pyin algorithm for accurate pitch tracking.
        Returns a 1D numpy array of F0 values (Hz), zeros indicate unvoiced frames.
        """
        f0, voiced_flag, voiced_probs = librosa.pyin(
            audio,
            fmin=float(librosa.note_to_hz('C2')),  # ~65 Hz (low bound)
            fmax=float(librosa.note_to_hz('C7')),  # ~2093 Hz (high bound)
            sr=self.SAMPLE_RATE
        )
        # Replace NaN (unvoiced) with 0 for processing
        f0 = np.nan_to_num(f0, nan=0.0)
        self.last_f0 = f0
        return f0

    def classify_tone(self, f0: np.ndarray) -> int:
        """
        Classifies the Mandarin tone based on the F0 pitch contour.

        Returns an integer from 1 to 5 representing the tone:
          1 = Flat (High)
          2 = Rising
          3 = Falling-Rising (Dipping)
          4 = Falling
          5 = Neutral (unable to classify clearly)
        """
        # Filter out zero (unvoiced) frames
        voiced = f0[f0 > 0]
        if len(voiced) < 5:
            # Not enough voiced content — cannot classify
            return 5

        # Normalize to 0-1 range for shape comparison
        f0_min, f0_max = voiced.min(), voiced.max()
        if f0_max - f0_min < 20:  # Very flat pitch range — Tone 1
            return 1

        normalized = (voiced - f0_min) / (f0_max - f0_min + 1e-6)

        # Split into first half and second half
        mid = len(normalized) // 2
        first_half = normalized[:mid]
        second_half = normalized[mid:]

        first_avg = first_half.mean()
        second_avg = second_half.mean()

        # Find the minimum point (for tone 3 dip detection)
        min_idx = np.argmin(normalized)
        min_ratio = min_idx / len(normalized)

        if second_avg > first_avg + 0.2:
            # Rising pattern: start low, end high → Tone 2
            return 2
        elif min_ratio > 0.2 and min_ratio < 0.8 and normalized[0] > 0.3 and normalized[-1] > 0.3:
            # Dipping in the middle → Tone 3
            return 3
        elif first_avg > second_avg + 0.2:
            # Falling pattern: start high, end low → Tone 4
            return 4
        else:
            # Neutral / unclear
            return 5

    def analyze_from_microphone(self) -> dict:
        """
        Full pipeline: record → extract F0 → classify tone.
        Returns a dict with:
          - 'tone': int (1-5)
          - 'tone_name': str (e.g., 'Tone 1 (Flat)')
          - 'f0': np.ndarray of pitch values
          - 'accuracy': float (0.0 to 1.0, simulated for now)
        """
        audio = self.record_audio()
        f0 = self.extract_f0(audio)
        tone = self.classify_tone(f0)

        tone_names = {
            1: "Tone 1 — High Flat (阴平)",
            2: "Tone 2 — Rising (阳平)",
            3: "Tone 3 — Falling-Rising (上声)",
            4: "Tone 4 — Falling (去声)",
            5: "Tone 5 — Neutral (轻声)",
        }

        return {
            "tone": tone,
            "tone_name": tone_names.get(tone, "Unknown"),
            "f0": f0,
            "accuracy": self._estimate_accuracy(f0, tone)
        }

    def _estimate_accuracy(self, f0: np.ndarray, detected_tone: int) -> float:
        """
        Estimates pronunciation accuracy based on how cleanly the pitch
        contour matches the expected pattern for the detected tone.
        Returns a float between 0.0 and 1.0.
        """
        voiced = f0[f0 > 0]
        if len(voiced) < 5:
            return 0.0

        normalized = (voiced - voiced.min()) / (voiced.max() - voiced.min() + 1e-6)
        smoothness = 1.0 - np.std(np.diff(normalized))
        # Clamp between 0 and 1
        return float(np.clip(smoothness, 0.0, 1.0))
