"""
ai/tutor.py
------------
The AI Tutor module — the brain of the application.

By default, this module uses a simulated (local) AI tutor that responds
with rule-based feedback. To use a real OpenAI or DeepSeek API, replace
the _call_simulated_ai() method with _call_openai_api() and provide
an API key via environment variable OPENAI_API_KEY.

Architecture:
  - AiTutor class manages conversation history + progress tracking
  - generate_response(user_input, context) → returns feedback string
  - generate_exercise(level) → returns a new exercise dict
  - update_progress(result) → adjusts difficulty level based on results
"""

import os
import random
from utils.pinyin_utils import get_vocabulary, get_tone_info


class AITutor:
    """
    AI Tutor that teaches Mandarin tones with adaptive feedback.

    Tracks user performance across sessions and adjusts difficulty
    automatically. Can be backed by a real LLM API or run in
    simulated mode for offline use.
    """

    LEVELS = ["beginner", "intermediate", "advanced"]

    # Error threshold: if accuracy drops below this, lower the difficulty
    LEVEL_DOWN_THRESHOLD = 0.4
    # Success threshold: if accuracy exceeds this consistently, raise difficulty
    LEVEL_UP_THRESHOLD = 0.75

    def __init__(self, api_key: str | None = None, use_real_ai: bool = False):
        """
        Args:
            api_key: OpenAI or DeepSeek API key (optional).
            use_real_ai: If True, uses the real API. If False, uses simulation.
        """
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY")
        self.use_real_ai = use_real_ai and self.api_key is not None

        # Conversation history for multi-turn context
        self.conversation_history: list[dict] = []

        # User progress tracking
        self.current_level = "beginner"
        self.session_results: list[float] = []       # List of accuracy floats
        self.correct_streak = 0
        self.wrong_streak = 0

        print(f"[AITutor] Initialized. Mode: {'Real API' if self.use_real_ai else 'Simulated'}")

    # ─────────────────────────────────────────────
    # Public Methods
    # ─────────────────────────────────────────────

    def generate_response(self, user_input: str, context: dict | None = None) -> str:
        """
        Generates a tutor response given user input and optional context.

        Context keys (optional):
          - 'detected_tone': int — the tone the system detected
          - 'expected_tone': int — the tone the user was supposed to produce
          - 'accuracy': float — pronunciation accuracy score (0-1)
          - 'character': str — the character being practiced
        """
        self.conversation_history.append({"role": "user", "content": user_input})

        if self.use_real_ai:
            response = self._call_real_api(user_input, context)
        else:
            response = self._simulated_response(user_input, context)

        self.conversation_history.append({"role": "assistant", "content": response})
        return response

    def generate_exercise(self) -> dict:
        """
        Generates a pronunciation exercise appropriate for the current difficulty level.

        Returns a dict:
          {
            'character': str,
            'pinyin': str,
            'meaning': str,
            'tones': list[int],
            'instruction': str
          }
        """
        vocab = get_vocabulary(self.current_level)
        word = random.choice(vocab)
        instruction = (
            f"Please pronounce the word: '{word['character']}' ({word['pinyin']}) "
            f"which means '{word['meaning']}'. "
            f"The tone(s) are: {', '.join([get_tone_info(t)['name'] for t in word['tones']])}."
        )
        return {**word, "instruction": instruction}

    def update_progress(self, accuracy: float, was_correct: bool):
        """
        Records the result of a user attempt and adjusts difficulty level.

        Args:
            accuracy: Float 0.0 - 1.0 from the tone analyzer.
            was_correct: Whether the user matched the expected tone.
        """
        self.session_results.append(accuracy)

        if was_correct:
            self.correct_streak += 1
            self.wrong_streak = 0
        else:
            self.wrong_streak += 1
            self.correct_streak = 0

        # Adaptive difficulty adjustment
        if self.correct_streak >= 3:
            self._level_up()
            self.correct_streak = 0
        elif self.wrong_streak >= 3:
            self._level_down()
            self.wrong_streak = 0

    def get_progress_summary(self) -> str:
        """Returns a human-readable summary of current session progress."""
        if not self.session_results:
            return "No attempts yet this session."

        avg = sum(self.session_results) / len(self.session_results)
        return (
            f"📊 Session Summary:\n"
            f"  Attempts: {len(self.session_results)}\n"
            f"  Average Accuracy: {avg:.0%}\n"
            f"  Current Level: {self.current_level.capitalize()}\n"
            f"  Correct Streak: {self.correct_streak} | Wrong Streak: {self.wrong_streak}"
        )

    # ─────────────────────────────────────────────
    # Private / Internal Methods
    # ─────────────────────────────────────────────

    def _level_up(self):
        idx = self.LEVELS.index(self.current_level)
        if idx < len(self.LEVELS) - 1:
            self.current_level = self.LEVELS[idx + 1]
            print(f"[AITutor] Level up! Now: {self.current_level}")

    def _level_down(self):
        idx = self.LEVELS.index(self.current_level)
        if idx > 0:
            self.current_level = self.LEVELS[idx - 1]
            print(f"[AITutor] Level down. Now: {self.current_level}")

    def _simulated_response(self, user_input: str, context: dict | None) -> str:
        """
        Rule-based simulated AI response when no API key is available.
        Generates contextual feedback based on tone detection results.
        """
        ctx = context or {}
        detected = ctx.get("detected_tone")
        expected = ctx.get("expected_tone")
        accuracy = ctx.get("accuracy", 0.0)
        character = ctx.get("character", "this character")

        # Greeting / general messages
        greetings = ["你好", "hello", "hi", "start", "begin", "nǐ hǎo"]
        if any(g in user_input.lower() for g in greetings):
            return (
                "你好！Welcome to your Mandarin lesson! 😊\n\n"
                "I'm your AI tutor. Let's start with the 4 tones of Mandarin:\n\n"
                "  1️⃣ Tone 1 (ā): High and flat — like a flat line ——\n"
                "  2️⃣ Tone 2 (á): Rising — like asking 'What?' /\n"
                "  3️⃣ Tone 3 (ǎ): Falling then rising — like a valley ∨\n"
                "  4️⃣ Tone 4 (à): Sharp falling — like saying 'No!' \\\n"
                "  5️⃣ Neutral: Short and unstressed ·\n\n"
                "Click 'New Exercise' to begin practicing!"
            )

        # Tone correction feedback
        if detected is not None and expected is not None:
            if detected == expected:
                return self._correct_feedback(expected, accuracy)
            else:
                return self._incorrect_feedback(detected, expected, accuracy, character)

        # General question fallback
        return self._general_fallback(user_input)

    def _correct_feedback(self, tone: int, accuracy: float) -> str:
        tone_info = get_tone_info(tone)
        if accuracy > 0.8:
            responses = [
                f"🎉 Excellent! Your {tone_info['name']} is spot-on! Keep it up!",
                f"✅ Perfect! That was a clear {tone_info['name']}. Great job!",
                f"💯 Amazing pronunciation of {tone_info['name']}! You're a natural!",
            ]
        else:
            responses = [
                f"✅ Correct tone! That was {tone_info['name']}. Try to make it a bit cleaner next time.",
                f"👍 Good! You got {tone_info['name']} right. Aim for more consistency.",
            ]
        return random.choice(responses)

    def _incorrect_feedback(self, detected: int, expected: int, accuracy: float, character: str) -> str:
        detected_info = get_tone_info(detected)
        expected_info = get_tone_info(expected)
        return (
            f"🔄 Not quite! I detected {detected_info['name']}, but you were aiming for {expected_info['name']}.\n\n"
            f"💡 Tip for {expected_info['name']}:\n"
            f"   \"{expected_info['description']}\"\n\n"
            f"   Example: '{expected_info['example_pinyin']}' ({expected_info['example_character']}) = {expected_info['example_meaning']}\n\n"  # noqa: E501
            f"Try again — you can do it! 加油！"
        )

    def _general_fallback(self, user_input: str) -> str:
        hints = [
            "Try clicking '🎤 Record & Analyze' to practice your pronunciation!",
            "Ask me about any tone — I can explain Tone 1, 2, 3, 4, or the neutral tone.",
            "Switch to the '✍️ Writing' tab to practice stroke order!",
            "Click 'New Exercise' for a new word to practice.",
        ]
        return f"🤖 I'm here to help you learn Mandarin!\n\n💡 Hint: {random.choice(hints)}"

    def _call_real_api(self, user_input: str, context: dict | None) -> str:
        """
        Calls the real OpenAI API (or DeepSeek-compatible) for a response.
        Requires: pip install openai
        Set env var: OPENAI_API_KEY=your_key
                     OPENAI_BASE_URL=https://api.deepseek.com (for DeepSeek)
        """
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=self.api_key,
                base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            )

            # Build the system prompt
            system_prompt = (
                "You are an expert Mandarin Chinese language tutor. "
                "You are teaching a complete beginner the 4 tones of Mandarin. "
                "Be encouraging, concise, and always give practical tips. "
                "Use emoji occasionally to be friendly. "
                "When relevant, reference the context data provided."
            )
            if context:
                ctx_str = ", ".join(f"{k}={v}" for k, v in context.items())
                system_prompt += f"\n\nContext from tone detection system: {ctx_str}"

            messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
            for msg in self.conversation_history[-8:]:
                messages.append({"role": msg["role"], "content": str(msg["content"])})

            response = client.chat.completions.create(
                model=os.environ.get("AI_MODEL", "gpt-4o-mini"),
                messages=messages,  # type: ignore
                temperature=0.7,
                max_tokens=300
            )
            return response.choices[0].message.content or ""

        except ImportError:
            return "[Error] openai package not installed. Run: pip install openai"
        except Exception as e:
            return f"[API Error] {str(e)}\n\nFalling back to simulated response:\n" + self._simulated_response(user_input, context)  # noqa: E501
