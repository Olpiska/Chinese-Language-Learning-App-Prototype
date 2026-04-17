"""
writing/evaluator.py
---------------------
Evaluates user-drawn Chinese characters by comparing their strokes
against a reference database using geometric similarity.

The evaluation pipeline:
  1. User draws on a canvas → captures a list of (x, y) stroke paths
  2. Each stroke is normalized to a 0–1 coordinate space
  3. Strokes are compared against reference strokes using DTW-lite distance
  4. An accuracy score (0.0 to 1.0) is returned with feedback

Note: This module uses a simple spatial comparison. For production-level
accuracy, a deep learning OCR/computer vision model would be preferred.
"""

import numpy as np
from utils.pinyin_utils import get_stroke_data


class StrokeEvaluator:
    """
    Evaluates the similarity between a user's drawn strokes and
    the reference strokes stored for a given character.
    """

    # Maximum allowed distance penalty per stroke (for normalization)
    MAX_STROKE_DISTANCE = 180.0

    def __init__(self):
        pass

    def evaluate(self, character: str, user_strokes: list) -> dict:
        """
        Compares user strokes against the reference data for a character.

        Args:
            character: The Chinese character (str) to evaluate against.
            user_strokes: List of strokes. Each stroke is a list of (x, y) tuples.
                          Coordinates should be in the 0–100 range (percentage of canvas size).

        Returns a dict:
          {
            'score': float (0.0 to 1.0),
            'stroke_scores': list[float],
            'feedback': str,
            'missing_strokes': int,
            'extra_strokes': int
          }
        """
        reference_strokes = get_stroke_data(character)

        if not reference_strokes:
            return {
                "score": 0.0,
                "stroke_scores": [],
                "feedback": f"⚠️ No reference stroke data found for '{character}'. Try a simpler character.",
                "missing_strokes": 0,
                "extra_strokes": 0
            }

        if not user_strokes:
            return {
                "score": 0.0,
                "stroke_scores": [],
                "feedback": "❌ No strokes detected. Draw the character on the canvas!",
                "missing_strokes": len(reference_strokes),
                "extra_strokes": 0
            }

        # Count stroke differences
        ref_count = len(reference_strokes)
        user_count = len(user_strokes)
        missing = max(0, ref_count - user_count)
        extra = max(0, user_count - ref_count)

        # Compare stroke by stroke (pair up as many as we can)
        pairs = min(ref_count, user_count)
        stroke_scores = []
        for i in range(pairs):
            ref_stroke = np.array(reference_strokes[i], dtype=float)
            user_stroke = np.array(user_strokes[i], dtype=float)
            distance = self._stroke_distance(ref_stroke, user_stroke)
            # Convert distance to a 0-1 score
            score = max(0.0, 1.0 - distance / self.MAX_STROKE_DISTANCE)
            stroke_scores.append(score)

        # Add zero scores for missing strokes
        stroke_scores.extend([0.0] * missing)

        overall_score = sum(stroke_scores) / ref_count if ref_count > 0 else 0.0
        feedback = self._generate_feedback(overall_score, missing, extra)

        return {
            "score": overall_score,
            "stroke_scores": stroke_scores,
            "feedback": feedback,
            "missing_strokes": missing,
            "extra_strokes": extra
        }

    def _stroke_distance(self, ref: np.ndarray, user: np.ndarray) -> float:
        """
        Computes a simplified DTW-like distance between two stroke paths.
        Both inputs are Nx2 numpy arrays of (x, y) points.
        The user stroke is resampled to match the reference length.
        """
        # Resample user stroke to same number of points as reference
        user_resampled = self._resample_stroke(user, len(ref))

        # Compute mean Euclidean distance point by point
        distances = np.linalg.norm(ref - user_resampled, axis=1)
        return float(distances.mean())

    def _resample_stroke(self, stroke: np.ndarray, n: int) -> np.ndarray:
        """
        Resamples a stroke (Mx2 array) to exactly n evenly-spaced points
        using linear interpolation along the stroke's path.
        """
        if len(stroke) == n:
            return stroke
        if len(stroke) == 1:
            return np.tile(stroke, (n, 1))

        # Compute cumulative arc length
        diffs = np.diff(stroke, axis=0)
        seg_lengths = np.linalg.norm(diffs, axis=1)
        cumulative = np.concatenate([[0], np.cumsum(seg_lengths)])
        total_length = cumulative[-1]

        if total_length == 0:
            return np.tile(stroke[0], (n, 1))

        # New evenly-spaced parameter values
        new_params = np.linspace(0, total_length, n)
        # Interpolate x and y independently
        new_x = np.interp(new_params, cumulative, stroke[:, 0])
        new_y = np.interp(new_params, cumulative, stroke[:, 1])
        return np.column_stack([new_x, new_y])

    def _generate_feedback(self, score: float, missing: int, extra: int) -> str:
        """Generates human-readable feedback based on stroke evaluation."""
        parts = []

        if score >= 0.85:
            parts.append("🎉 Excellent! Your stroke order and direction are great!")
        elif score >= 0.65:
            parts.append("✅ Good job! The character is recognizable. Keep practicing for precision.")
        elif score >= 0.40:
            parts.append("👍 Decent attempt! Focus on stroke direction and proportion.")
        else:
            parts.append("❌ Needs practice. Watch the stroke order animation and try again.")

        if missing > 0:
            parts.append(f"⚠️ You missed {missing} stroke(s) — the character has more strokes!")
        if extra > 0:
            parts.append(f"⚠️ You drew {extra} extra stroke(s) — be careful not to add extra marks.")

        parts.append(f"📊 Score: {score:.0%}")
        return "\n".join(parts)
