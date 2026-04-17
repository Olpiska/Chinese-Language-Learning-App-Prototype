"""
utils/progress.py
------------------
XP-based level system and quiz generator.

- Tracks words practiced, XP earned, current level
- Generates a 5-question quiz after every 5 completed words
- Saves/loads progress to a local JSON file
"""

import json
import random
from pathlib import Path
from utils.config import get_appdata_dir

# Level thresholds (XP required to reach each level)
LEVELS = [
    {"level": 1, "name": "Beginner", "xp_required": 0},
    {"level": 2, "name": "Novice", "xp_required": 50},
    {"level": 3, "name": "Elementary", "xp_required": 120},
    {"level": 4, "name": "Pre-Intermediate", "xp_required": 230},
    {"level": 5, "name": "Intermediate", "xp_required": 400},
    {"level": 6, "name": "Upper-Intermed.", "xp_required": 650},
    {"level": 7, "name": "Advanced", "xp_required": 1000},
    {"level": 8, "name": "Expert", "xp_required": 1500},
    {"level": 9, "name": "Master", "xp_required": 2200},
    {"level": 10, "name": "Grandmaster", "xp_required": 3000},
]

XP_PER_CORRECT_TONE = 10   # Pronunciation exercise correct
XP_PER_WRONG_TONE = 2      # Tried even if wrong
XP_PER_WRITING = 5         # Attempted a writing exercise
XP_PER_QUIZ_CORRECT = 20   # Quiz question correct
QUIZ_EVERY_N_WORDS = 5     # Trigger quiz after this many completed words

SAVE_PATH = get_appdata_dir() / "progress.json"


class ProgressTracker:
    """
    Manages XP, level, word completion count, and quiz triggering.
    Persists data to a local JSON file.
    """

    def __init__(self):
        self.xp = 0
        self.words_completed = 0
        self.words_since_last_quiz = 0
        self.correct_streak = 0
        self.session_correct = 0
        self.session_attempts = 0
        self.quiz_pending = False          # True when a quiz should be triggered
        self._load()

    # ─────────────────────────────────────────────
    # Core XP / Level Methods
    # ─────────────────────────────────────────────

    def add_xp(self, amount: int):
        """Adds or subtracts XP and checks for level up (floored at 0)."""
        self.xp = max(0, self.xp + amount)
        self._save()

    def get_level_info(self) -> dict:
        """Returns current level info dict from LEVELS."""
        current = LEVELS[0]
        for lvl in LEVELS:
            if self.xp >= lvl["xp_required"]:
                current = lvl
            else:
                break
        return current

    def get_next_level_info(self) -> dict | None:
        """Returns the next level's info, or None if at max."""
        current = self.get_level_info()
        idx = next((i for i, l in enumerate(LEVELS) if l["level"] == current["level"]), 0)
        if idx + 1 < len(LEVELS):
            return LEVELS[idx + 1]
        return None

    def get_xp_progress_pct(self) -> float:
        """Returns 0.0-1.0 progress toward next level."""
        current = self.get_level_info()
        nxt = self.get_next_level_info()
        if nxt is None:
            return 1.0
        span = nxt["xp_required"] - current["xp_required"]
        earned = self.xp - current["xp_required"]
        return min(1.0, earned / span) if span > 0 else 1.0

    def get_vocab_level(self) -> str:
        """Maps level number to vocabulary difficulty."""
        lvl = self.get_level_info()["level"]
        if lvl <= 3:
            return "beginner"
        elif lvl <= 6:
            return "intermediate"
        else:
            return "advanced"

    # ─────────────────────────────────────────────
    # Word Completion & Quiz Trigger
    # ─────────────────────────────────────────────

    def record_pronunciation_attempt(self, accuracy: float) -> bool:
        """
        Records a pronunciation attempt with stricter XP rules:
        - accuracy >= 0.90: +10 XP
        - accuracy < 0.80: -5 XP
        Returns True if a quiz should now be triggered.
        """
        self.session_attempts += 1

        if accuracy >= 0.90:
            self.session_correct += 1
            self.words_completed += 1
            self.words_since_last_quiz += 1
            self.add_xp(XP_PER_CORRECT_TONE)
        elif accuracy < 0.80:
            self.add_xp(-5)  # Penalty for poor performance
        else:
            # 0.80 <= accuracy < 0.90: No XP change
            pass

        # Check quiz trigger
        if self.words_since_last_quiz >= QUIZ_EVERY_N_WORDS:
            self.words_since_last_quiz = 0
            self.quiz_pending = True
            return True
        return False

    def record_writing_attempt(self, score: float):
        """
        Records a writing exercise attempt with stricter XP rules:
        - score >= 0.90: reward
        - score < 0.80: penalty
        """
        if score >= 0.90:
            xp = int(XP_PER_WRITING * score)
            self.add_xp(xp)
        elif score < 0.80:
            self.add_xp(-3)  # Small penalty for writing mistakes
        else:
            # Neutral zone: 0.80 - 0.90
            pass

    def record_quiz_result(self, correct: bool):
        """Records a quiz answer result."""
        if correct:
            self.add_xp(XP_PER_QUIZ_CORRECT)

    def clear_quiz_pending(self):
        self.quiz_pending = False

    # ─────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────

    def get_summary_text(self) -> str:
        lvl = self.get_level_info()
        nxt = self.get_next_level_info()
        acc = (self.session_correct / self.session_attempts * 100) if self.session_attempts else 0
        next_str = f"{nxt['name']} at {nxt['xp_required']} XP" if nxt else "MAX LEVEL!"
        return (
            f"Level {lvl['level']}: {lvl['name']}\n"
            f"XP: {self.xp} | Next: {next_str}\n"
            f"Words completed: {self.words_completed}\n"
            f"Session: {self.session_correct}/{self.session_attempts} correct ({acc:.0f}%)"
        )

    # ─────────────────────────────────────────────
    # Persistence
    # ─────────────────────────────────────────────

    def _save(self):
        data = {
            "xp": self.xp,
            "words_completed": self.words_completed,
            "words_since_last_quiz": self.words_since_last_quiz,
        }
        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[Progress] Could not save: {e}")

    def _load(self):
        if SAVE_PATH.exists():
            try:
                with open(SAVE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.xp = data.get("xp", 0)
                self.words_completed = data.get("words_completed", 0)
                self.words_since_last_quiz = data.get("words_since_last_quiz", 0)
                print(f"[Progress] Loaded: XP={self.xp}, words={self.words_completed}")
            except Exception as e:
                print(f"[Progress] Could not load: {e}")


# ─────────────────────────────────────────────────────────────
# Quiz Generator
# ─────────────────────────────────────────────────────────────

TONE_OPTIONS = {
    1: "Tone 1 — High Flat (ma)",
    2: "Tone 2 — Rising (ma/)",
    3: "Tone 3 — Dipping (mav)",
    4: "Tone 4 — Falling (ma\\)",
    5: "Neutral — Short unstressed",
}


class QuizGenerator:
    """Generates 5-question tone quizzes from the current vocabulary."""

    def __init__(self, vocab: list):
        self.vocab = vocab

    def generate_quiz(self, n: int = 5) -> list:
        """
        Returns a list of n quiz question dicts:
        {
          'character': str,
          'pinyin': str,
          'meaning': str,
          'syllable_index': int,      # which syllable to identify (0-based)
          'correct_tone': int,        # 1-5
          'choices': list[dict],      # 4 choices: {'tone': int, 'label': str}
        }
        """
        questions = []
        pool = random.sample(self.vocab, min(n, len(self.vocab)))
        for word in pool:
            tones = word.get("tones", [1])
            # Pick a random syllable if multi-character
            syl_idx = random.randint(0, len(tones) - 1)
            correct = tones[syl_idx]

            # Build 4 choices (correct + 3 wrong)
            wrong_pool = [t for t in range(1, 6) if t != correct]
            wrongs = random.sample(wrong_pool, min(3, len(wrong_pool)))
            choices = [correct] + wrongs
            random.shuffle(choices)

            questions.append({
                "character": word["character"],
                "pinyin": word["pinyin"],
                "meaning": word["meaning"],
                "syllable_index": syl_idx,
                "correct_tone": correct,
                "choices": [{"tone": t, "label": TONE_OPTIONS[t]} for t in choices],
            })
        return questions
