"""
ui/main_window.py  (v2 — Enhanced)
------------------------------------
New in this version:
  1. Ghost/transparent character overlay on writing canvas
  2. XP-based level system with progress bar in header
  3. Quiz dialog (every 5 completed words)
  4. Word-level tone breakdown (pinyin per syllable with tone explanation)
"""

import os
import threading
import numpy as np
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTabWidget, QTextEdit,
    QLineEdit, QComboBox, QProgressBar, QFrame,
    QSizePolicy, QScrollArea, QDialog, QButtonGroup,
    QRadioButton, QListWidget, QListWidgetItem, QToolButton, QGridLayout,
    QSystemTrayIcon, QMenu, QMessageBox, QCheckBox
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QUrl
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QFont,
    QPainterPath, QPixmap, QAction, QIcon
)

from utils.config import SETTINGS, resource_path, get_appdata_dir
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from audio.tts import TTSEngine
from audio.tone_analyzer import ToneAnalyzer
from ai.tutor import AITutor
from writing.evaluator import StrokeEvaluator
from utils.pinyin_utils import get_tone_info, get_stroke_data, get_vocabulary, VOCABULARY, search_dictionary
from utils.hsk_vocab import get_hsk_vocabulary
from utils.progress import ProgressTracker, QuizGenerator
from utils.story_data import get_stories


# ──────────────────────────────────────────────
# Background worker for audio recording
# ──────────────────────────────────────────────
class RecordingWorker(QThread):
    result_ready = pyqtSignal(dict)

    def __init__(self, analyzer: ToneAnalyzer):
        super().__init__()
        self.analyzer = analyzer

    def run(self):
        result = self.analyzer.analyze_from_microphone()
        self.result_ready.emit(result)


# ──────────────────────────────────────────────
# Drawing Canvas with Ghost Character Overlay
# ──────────────────────────────────────────────
class DrawingCanvas(QWidget):
    """
    Mouse-drawing canvas for Chinese characters.
    Shows a translucent 'ghost' of the target character behind user strokes.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(300, 300)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self.strokes: List[List[Tuple[float, float]]] = []
        self.current_stroke: List[Tuple[float, float]] = []
        self.reference_strokes: List[List[Tuple[float, float]]] = []
        self.ghost_character = ""   # The target Chinese character shown as ghost
        self.show_reference = False
        self.drawing = False

        self.background_pixmap = QPixmap()
        self.show_image_hint = True

        # Tutorial Animation State
        self.animation_timer = QTimer()
        self.animation_timer.timeout.connect(self._animate_step)
        self.animated_strokes = []
        self.anim_stroke_idx = 0
        self.anim_point_idx = 0
        self.is_animating = False

    def set_ghost_character(self, char: str):
        """Sets the transparent character shown behind user strokes."""
        self.ghost_character = char
        self.update()

    def set_background_image(self, image_path: str):
        """Sets a mnemonic image as the background hint."""
        if image_path and os.path.exists(image_path):
            self.background_pixmap = QPixmap(image_path)
            print(f"[DrawingCanvas] Loaded image: {image_path} (exists? {os.path.exists(image_path)})")
        else:
            if image_path:
                print(f"[DrawingCanvas] Image NOT found: {image_path}")
            self.background_pixmap = QPixmap()
        self.update()

    def set_reference_strokes(self, strokes: list, show: bool = True):
        self.reference_strokes = self._normalize_reference_strokes(strokes)
        self.show_reference = show
        self.update()

    def _normalize_reference_strokes(self, strokes: list) -> list:
        """
        Cleans and normalizes stroke coordinates into a stable 0..100 canvas box.
        This prevents malformed reference data from appearing squashed or off-canvas.
        """
        cleaned: list[list[tuple[float, float]]] = []

        # 1) Keep only valid numeric points and remove near-duplicates.
        for stroke in strokes or []:
            pts: list[tuple[float, float]] = []
            for p in stroke:
                if not isinstance(p, (list, tuple)) or len(p) < 2:
                    continue
                try:
                    x = float(p[0])
                    y = float(p[1])
                except Exception:
                    continue
                if not np.isfinite(x) or not np.isfinite(y):
                    continue
                if not pts:
                    pts.append((x, y))
                    continue
                px, py = pts[-1]
                if abs(x - px) + abs(y - py) >= 0.4:
                    pts.append((x, y))
            if len(pts) >= 2:
                cleaned.append(pts)

        if not cleaned:
            return []

        # 2) Compute bounds and normalize to a centered inner box.
        all_pts = [pt for stroke in cleaned for pt in stroke]
        xs = [p[0] for p in all_pts]
        ys = [p[1] for p in all_pts]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        span_x = max(max_x - min_x, 1e-6)
        span_y = max(max_y - min_y, 1e-6)

        margin = 12.0
        target = 100.0 - (2.0 * margin)
        scale = min(target / span_x, target / span_y)

        used_w = span_x * scale
        used_h = span_y * scale
        off_x = (100.0 - used_w) / 2.0
        off_y = (100.0 - used_h) / 2.0

        normalized: list[list[tuple[float, float]]] = []
        for stroke in cleaned:
            out_stroke: list[tuple[float, float]] = []
            for x, y in stroke:
                nx = (x - min_x) * scale + off_x
                ny = (y - min_y) * scale + off_y
                out_stroke.append((float(np.clip(nx, 0.0, 100.0)), float(np.clip(ny, 0.0, 100.0))))
            if len(out_stroke) >= 2:
                normalized.append(out_stroke)
        return normalized

    def clear(self):
        self.strokes = []
        self.current_stroke = []
        self.drawing = False
        self.is_animating = False
        self.animation_timer.stop()
        self.animated_strokes = []
        self.update()

    def start_tutorial(self):
        """Starts a step-by-step animation of the reference strokes."""
        if not self.reference_strokes:
            return

        self.is_animating = True
        self.anim_stroke_idx = 0
        self.anim_point_idx = 0
        self.animated_strokes = []
        self.strokes = []  # Clear user drawing
        self.animation_timer.start(30)  # 30ms per point

    def _animate_step(self):
        if not self.is_animating:
            return

        ref = self.reference_strokes
        if self.anim_stroke_idx >= len(ref):
            self.is_animating = False
            self.animation_timer.stop()
            return

        current_ref_stroke = ref[self.anim_stroke_idx]

        # Initialize new stroke if needed
        if self.anim_point_idx == 0:
            self.animated_strokes.append([])

        # Add point
        pt = current_ref_stroke[self.anim_point_idx]
        w, h = self.width(), self.height()
        self.animated_strokes[-1].append((pt[0] * w / 100.0, pt[1] * h / 100.0))

        self.anim_point_idx += 1
        if self.anim_point_idx >= len(current_ref_stroke):
            self.anim_point_idx = 0
            self.anim_stroke_idx += 1

        self.update()

    def get_normalized_strokes(self) -> list:
        w, h = self.width(), self.height()
        return [
            [(x * 100.0 / w, y * 100.0 / h) for (x, y) in stroke]
            for stroke in self.strokes
        ]

    def mousePressEvent(self, a0):
        if a0 and a0.button() == Qt.MouseButton.LeftButton:
            self.drawing = True
            self.current_stroke = [(a0.position().x(), a0.position().y())]

    def mouseMoveEvent(self, a0):
        if a0 and self.drawing:
            self.current_stroke.append((a0.position().x(), a0.position().y()))
            self.update()

    def mouseReleaseEvent(self, a0):
        if a0 and a0.button() == Qt.MouseButton.LeftButton and self.drawing:
            self.drawing = False
            if self.current_stroke:
                self.strokes.append(self.current_stroke)
                self.current_stroke = []

    def paintEvent(self, a0):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Background
        painter.fillRect(self.rect(), QColor("#1a1a2e"))

        w, h = self.width(), self.height()

        # ── Background Image Mnemonic (Subtle) ──
        if self.show_image_hint and not self.background_pixmap.isNull():
            painter.setOpacity(0.4)  # Increased visibility
            # Scale to fit while keeping aspect ratio
            scaled = self.background_pixmap.scaled(
                w - 40, h - 40,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(
                (w - scaled.width()) // 2,
                (h - scaled.height()) // 2,
                scaled
            )
            painter.setOpacity(1.0)  # Reset opacity for strokes

        # ── Ghost character (translucent behind everything) ──
        if self.ghost_character:
            # Shrink more to stay within 10-90% range of the evaluator
            font_size = max(1, int(min(w, h) * 0.65))
            ghost_font = QFont("Microsoft YaHei UI", font_size)
            ghost_font.setWeight(QFont.Weight.Light)
            painter.setFont(ghost_font)
            painter.setPen(QColor(200, 180, 255, 35))   # Very transparent purple
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.ghost_character)

        # ── Reference strokes (dashed guide lines) ──
        if self.show_reference and self.reference_strokes:
            ref_pen = QPen(QColor(80, 80, 200, 100), 3, Qt.PenStyle.DashLine)
            painter.setPen(ref_pen)
            for stroke in self.reference_strokes:
                if len(stroke) < 2:
                    continue
                path = QPainterPath()
                path.moveTo(stroke[0][0] * w / 100.0, stroke[0][1] * h / 100.0)
                for i in range(1, len(stroke)):
                    px, py = stroke[i]
                    path.lineTo(px * w / 100.0, py * h / 100.0)
                painter.drawPath(path)

        # ── Completed user strokes ──
        user_pen = QPen(QColor("#e0aaff"), 4, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(user_pen)
        for stroke in self.strokes:
            if len(stroke) < 2:
                continue
            path = QPainterPath()  # Create path for completed stroke
            path.moveTo(*stroke[0])
            for i in range(1, len(stroke)):
                path.lineTo(*stroke[i])
            painter.drawPath(path)

        # ── Active stroke ──
        active_pen = QPen(QColor("#c77dff"), 4, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(active_pen)
        if len(self.current_stroke) >= 2:
            path = QPainterPath()
            path.moveTo(*self.current_stroke[0])
            for i in range(1, len(self.current_stroke)):
                path.lineTo(*self.current_stroke[i])
            painter.drawPath(path)

        # ── Tutorial / Animated strokes ──
        if self.is_animating and self.animated_strokes:
            anim_pen = QPen(QColor("#ffea00"), 6, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(anim_pen)
            for stroke in self.animated_strokes:
                if len(stroke) < 2:
                    continue
                path = QPainterPath()
                path.moveTo(*stroke[0])
                for point in stroke[1:]:
                    path.lineTo(*point)
                painter.drawPath(path)

        # ── Grid lines ──
        grid_pen = QPen(QColor(255, 255, 255, 18), 1, Qt.PenStyle.DotLine)
        painter.setPen(grid_pen)
        painter.drawLine(w // 2, 0, w // 2, h)
        painter.drawLine(0, h // 2, w, h // 2)

        painter.end()


# ──────────────────────────────────────────────
# Pitch Visualizer
# ──────────────────────────────────────────────
class PitchVisualizer(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(90)
        self.setMaximumHeight(110)
        self.f0_data = None
        self.tone_color = QColor("#c77dff")
        self.setStyleSheet("background: #0f0f1a; border-radius: 6px; border: 1px solid #333;")

    def set_data(self, f0: np.ndarray, tone: int):
        self.f0_data = f0
        tone_colors = {1: QColor("#72efdd"), 2: QColor("#48cae4"),
                       3: QColor("#f4a261"), 4: QColor("#e63946"), 5: QColor("#adb5bd")}
        self.tone_color = tone_colors.get(tone, QColor("#c77dff"))
        self.update()

    def paintEvent(self, a0):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0f0f1a"))
        if self.f0_data is None:
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Record to see pitch contour")
            painter.end()
            return
        voiced = self.f0_data[self.f0_data > 0]
        if len(voiced) < 2:
            painter.setPen(QColor(120, 120, 120))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Not enough voiced audio")
            painter.end()
            return
        w, h = self.width(), self.height()
        margin = 10
        f_min, f_max = voiced.min(), voiced.max()
        if f_max == f_min:
            f_max = f_min + 1
        pen = QPen(self.tone_color, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        path = QPainterPath()
        voiced_indices = [i for i, v in enumerate(self.f0_data) if v > 0]
        for j, idx in enumerate(voiced_indices):
            x = margin + (idx / len(self.f0_data)) * (w - 2 * margin)
            y = (h - margin) - ((self.f0_data[idx] - f_min) / (f_max - f_min)) * (h - 2 * margin)
            if j == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        painter.drawPath(path)
        painter.end()


# ──────────────────────────────────────────────
# Quiz Dialog
# ──────────────────────────────────────────────
class QuizDialog(QDialog):
    """
    A 5-question multiple-choice quiz about tones in context of real words.
    Shown after every 5 completed words.
    """

    def __init__(self, questions: list, progress: ProgressTracker, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mini Quiz — Tone Challenge!")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.questions = questions
        self.progress = progress
        self.current_q = 0
        self.score = 0
        self.selected_btn = None

        self._apply_style()
        self._build_ui()
        self._load_question()

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog { background: #0d0d1a; color: #e0e0e0; }
            QLabel { color: #e0e0e0; background: transparent; }
            QRadioButton { color: #ddd; font-size: 13px; padding: 8px; background: #11112a;
                           border-radius: 6px; margin: 3px; }
            QRadioButton:checked { color: #4aa3ff; border: 1px solid #4aa3ff; }
            QRadioButton:hover { background: #1a1a3e; }
            QPushButton { background: #2563eb; color: #fff; border: none; border-radius: 8px;
                          padding: 10px 20px; font-size: 13px; font-weight: bold; }
            QPushButton:hover { background: #1d4ed8; }
            QPushButton:disabled { background: #333; color: #666; }
        """)

    def _build_ui(self):
        self.layout_ = QVBoxLayout(self)
        self.layout_.setSpacing(12)
        self.layout_.setContentsMargins(24, 24, 24, 24)

        # Header
        self.header_label = QLabel()
        self.header_label.setStyleSheet("font-size: 11px; color: #888;")
        self.layout_.addWidget(self.header_label)

        # Question
        self.q_char = QLabel()
        self.q_char.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.q_char.setStyleSheet(
            "font-size: 64px; padding: 10px; color: #fff; background: #0a0a1f; border-radius: 8px;")
        self.layout_.addWidget(self.q_char)

        self.q_pinyin = QLabel()
        self.q_pinyin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.q_pinyin.setStyleSheet("font-size: 18px; color: #72efdd; font-weight: bold;")
        self.layout_.addWidget(self.q_pinyin)

        self.q_text = QLabel()
        self.q_text.setWordWrap(True)
        self.q_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.q_text.setStyleSheet("font-size: 13px; color: #ccc; margin-bottom: 8px;")
        self.layout_.addWidget(self.q_text)

        # Choices
        self.choice_group = QButtonGroup(self)
        self.choice_btns = []
        for i in range(4):
            btn = QRadioButton()
            self.choice_group.addButton(btn, i)
            self.layout_.addWidget(btn)
            self.choice_btns.append(btn)

        # Feedback
        self.feedback_label = QLabel("")
        self.feedback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.feedback_label.setStyleSheet("font-size: 13px; font-weight: bold; min-height: 24px;")
        self.layout_.addWidget(self.feedback_label)

        # Buttons
        btn_row = QHBoxLayout()
        self.check_btn = QPushButton("Check Answer")
        self.check_btn.clicked.connect(self._check_answer)
        self.next_btn = QPushButton("Next Question")
        self.next_btn.clicked.connect(self._next_question)
        self.next_btn.setEnabled(False)
        btn_row.addWidget(self.check_btn)
        btn_row.addWidget(self.next_btn)
        self.layout_.addLayout(btn_row)

    def _load_question(self):
        q = self.questions[self.current_q]
        n = len(self.questions)
        self.header_label.setText(f"Question {self.current_q + 1} of {n}  |  Score: {self.score}/{n}")

        # Highlight which syllable to identify
        char = q["character"]
        syl_idx = q["syllable_index"]
        # Show which syllable is being tested
        pinyin_parts = q["pinyin"].split()
        if len(pinyin_parts) > 1 and syl_idx < len(pinyin_parts):
            highlighted = " ".join(
                f"[{p}]" if i == syl_idx else p
                for i, p in enumerate(pinyin_parts)
            )
        else:
            highlighted = q["pinyin"]

        self.q_char.setText(char)
        self.q_pinyin.setText(highlighted)

        char_list = list(char)
        syllable = char_list[syl_idx] if syl_idx < len(char_list) else char
        self.q_text.setText(
            f'What tone is the highlighted syllable "{syllable}" in "{char}" ({q["meaning"]})?'
        )

        # Load choices
        for i, btn in enumerate(self.choice_btns):
            if i < len(q["choices"]):
                btn.setText(q["choices"][i]["label"])
                btn.setVisible(True)
                btn.setChecked(False)
                btn.setEnabled(True)
            else:
                btn.setVisible(False)

        self.feedback_label.setText("")
        self.check_btn.setEnabled(True)
        self.next_btn.setEnabled(False)

    def _check_answer(self):
        q = self.questions[self.current_q]
        checked_id = self.choice_group.checkedId()
        if checked_id < 0:
            self.feedback_label.setText("Please select an answer!")
            self.feedback_label.setStyleSheet("color: #f4a261; font-size: 13px; font-weight: bold;")
            return

        chosen_tone = q["choices"][checked_id]["tone"]
        correct = q["correct_tone"]

        # Disable all buttons after answering
        for btn in self.choice_btns:
            btn.setEnabled(False)

        if chosen_tone == correct:
            self.score += 1
            self.progress.record_quiz_result(True)
            self.feedback_label.setText("Correct! +20 XP")
            self.feedback_label.setStyleSheet("color: #72efdd; font-size: 13px; font-weight: bold;")
        else:
            correct_label = next(c["label"] for c in q["choices"] if c["tone"] == correct)
            self.feedback_label.setText(f"Wrong! Correct: {correct_label}")
            self.feedback_label.setStyleSheet("color: #e63946; font-size: 13px; font-weight: bold;")

        self.check_btn.setEnabled(False)
        self.next_btn.setEnabled(True)

    def _next_question(self):
        self.current_q += 1
        if self.current_q >= len(self.questions):
            self._finish()
        else:
            self._load_question()

    def _finish(self):
        n = len(self.questions)
        self.q_char.setText("Quiz Done!")
        self.q_pinyin.setText(f"Score: {self.score} / {n}")
        grade = "Excellent!" if self.score == n else ("Good job!" if self.score >= n * 0.6 else "Keep practicing!")
        self.q_text.setText(f"{grade} You earned {self.score * 20} XP from this quiz.")
        for btn in self.choice_btns:
            btn.setVisible(False)
        self.feedback_label.setText("")
        self.check_btn.setVisible(False)
        self.next_btn.setText("Close")
        self.next_btn.clicked.disconnect()
        self.next_btn.clicked.connect(self.accept)


# ──────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────
class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chinese Learning App")
        self.setMinimumSize(1100, 740)

        # ── Backend modules ──
        self.tts = TTSEngine()
        self.analyzer = ToneAnalyzer()
        api_key = os.environ.get("OPENAI_API_KEY")
        use_real = bool(api_key)
        self.tutor = AITutor(api_key=api_key, use_real_ai=use_real)
        self.evaluator = StrokeEvaluator()
        self.progress = ProgressTracker()

        # ── State ──
        self.current_exercise = None
        self.recording_worker = None
        self.last_user_wav_path = None
        self.practice_mode = "tones"  # 'tones' or 'hsk1'...'hsk10'
        self._meaning_src_text = ""
        self._meaning_translation_cache: dict[tuple[str, str], str] = {}

        self._audio_output = QAudioOutput()
        self._player = QMediaPlayer()
        self._player.setAudioOutput(self._audio_output)
        # Flatten all vocab into a pool for the quiz
        all_vocab = []
        for v in VOCABULARY.values():
            all_vocab.extend(v)
        self.quiz_gen = QuizGenerator(all_vocab)

        # Story Viewer State
        self.current_story = None
        self.current_page_idx = 0

        self._build_ui()
        self._apply_stylesheet()
        self._refresh_header()

        self._setup_tray_icon()
        self._setup_reminder()

        QTimer.singleShot(300, self._send_welcome)

    def _open_settings_dialog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Settings")
        dialog.setMinimumWidth(320)
        dialog.setStyleSheet("background: #0f172a; color: #eee; font-size: 13px;")
        layout = QVBoxLayout(dialog)
        
        lbl_rem = QLabel("Reminder System:")
        lbl_rem.setStyleSheet("font-weight: bold; color: #4aa3ff;")
        cb_rem = QCheckBox("Enable Background Practice Reminders")
        cb_rem.setChecked(SETTINGS.get("reminder_enabled"))
        
        lbl_close = QLabel("Window Close Behavior:")
        lbl_close.setStyleSheet("font-weight: bold; color: #4aa3ff;")
        combo_close = QComboBox()
        combo_close.addItems(["Ask every time", "Minimize to Tray", "Quit entirely"])
        
        mapping = {"ask": 0, "tray": 1, "quit": 2}
        combo_close.setCurrentIndex(mapping.get(SETTINGS.get("close_action"), 0))
        
        layout.addWidget(lbl_rem)
        layout.addWidget(cb_rem)
        layout.addSpacing(15)
        layout.addWidget(lbl_close)
        layout.addWidget(combo_close)
        layout.addStretch()
        
        btn_save = QPushButton("Save Settings")
        btn_save.setStyleSheet("background: #2b84d4; padding: 8px; border-radius: 6px; font-weight: bold;")
        btn_save.clicked.connect(lambda: dialog.accept())
        layout.addWidget(btn_save)
        
        if dialog.exec():
            SETTINGS.set("reminder_enabled", cb_rem.isChecked())
            actions = ["ask", "tray", "quit"]
            SETTINGS.set("close_action", actions[combo_close.currentIndex()])

    def closeEvent(self, event):
        action = SETTINGS.get("close_action")
        if action == "ask":
            cb = QCheckBox("Don't ask again")
            msg = QMessageBox(self)
            msg.setWindowTitle("Exit Options")
            msg.setText("Do you want to exit the app or minimize to tray?")
            msg.setIcon(QMessageBox.Icon.Question)
            btn_quit = msg.addButton("Quit", QMessageBox.ButtonRole.DestructiveRole)
            btn_tray = msg.addButton("Minimize to Tray", QMessageBox.ButtonRole.ActionRole)
            msg.setCheckBox(cb)
            msg.exec()
            
            if msg.clickedButton() == btn_tray:
                if cb.isChecked():
                    SETTINGS.set("close_action", "tray")
                event.ignore()
                self.hide()
                self.tray_icon.showMessage("China Learning App", "App is running in the background.", QSystemTrayIcon.MessageIcon.Information, 2000)
            else:
                if cb.isChecked():
                    SETTINGS.set("close_action", "quit")
                event.accept()
                
        elif action == "tray":
            event.ignore()
            self.hide()
            self.tray_icon.showMessage("China Learning App", "App minimized to tray.", QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            event.accept()

    def _setup_tray_icon(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        # Load an icon or create a dummy one
        try:
            icon_path = resource_path("res/img/cat_play.png")
            if os.path.exists(icon_path):
                self.tray_icon.setIcon(QIcon(icon_path))
            else:
                pm = QPixmap(32, 32)
                pm.fill(QColor("#4aa3ff"))
                self.tray_icon.setIcon(QIcon(pm))
        except Exception:
            pass

        tray_menu = QMenu()
        show_action = QAction("Show Application", self)
        show_action.triggered.connect(self.showNormal)
        quit_action = QAction("Quit Entirely", self)
        
        def _quit():
            import sys
            sys.exit(0)
            
        quit_action.triggered.connect(_quit)
        
        tray_menu.addAction(show_action)
        tray_menu.addSeparator()
        tray_menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self._on_tray_activated)
        self.tray_icon.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def _setup_reminder(self):
        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self._check_reminder)
        self.reminder_timer.start(1000 * 60 * 30) # Check every 30 minutes
        self.session_words_start = self.progress.words_completed

    def _check_reminder(self):
        if not SETTINGS.get("reminder_enabled"):
            return
            
        # Simplified memory check for demo
        if self.progress.words_completed == self.session_words_start:
            self.tray_icon.showMessage("Practice Time!", "You haven't practiced any words this session. How about a quick review?", QSystemTrayIcon.MessageIcon.Information, 5000)

    # ─────────────────────────────────────────────
    # Build UI
    # ─────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Header ──
        header = QWidget()
        header.setObjectName("header")
        header.setFixedHeight(70)
        h_row = QHBoxLayout(header)
        h_row.setContentsMargins(20, 6, 20, 6)

        title = QLabel("China Learning App")
        title.setObjectName("appTitle")
        h_row.addWidget(title)
        h_row.addStretch()

        # Settings button
        self.btn_settings = QPushButton("⚙ Settings")
        self.btn_settings.setObjectName("secondaryBtn")
        self.btn_settings.clicked.connect(self._open_settings_dialog)
        h_row.addWidget(self.btn_settings)

        h_row.addSpacing(20)

        # Level + XP section
        xp_col = QVBoxLayout()
        xp_col.setSpacing(2)

        self.level_label = QLabel("Level 1 — Beginner")
        self.level_label.setObjectName("levelDisplay")
        xp_col.addWidget(self.level_label)

        self.xp_bar = QProgressBar()
        self.xp_bar.setObjectName("xpBar")
        self.xp_bar.setFixedWidth(200)
        self.xp_bar.setFixedHeight(10)
        self.xp_bar.setRange(0, 100)
        self.xp_bar.setValue(0)
        self.xp_bar.setTextVisible(False)
        xp_col.addWidget(self.xp_bar)

        self.xp_label = QLabel("0 XP")
        self.xp_label.setStyleSheet("color: #888; font-size: 11px;")
        xp_col.addWidget(self.xp_label)

        h_row.addLayout(xp_col)
        root.addWidget(header)

        # ── Tabs ──
        self.tabs = QTabWidget()
        self.tabs.setObjectName("mainTabs")
        root.addWidget(self.tabs)

        self._build_pronunciation_tab()
        self._build_writing_tab()
        self._build_reading_tab()
        self._build_tutor_tab()

    # ─── Tab 1: Pronunciation & Tones ───

    def _build_pronunciation_tab(self):
        tab = QWidget()
        self.tabs.addTab(tab, "Pronunciation & Tones")
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── Left: Exercise ──
        left = QFrame()
        left.setObjectName("panel")
        left.setMaximumWidth(420)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(18, 18, 18, 18)
        ll.setSpacing(10)

        def QLabel_p(text, obj=None, style=None):
            return self._ql(ll, text, obj, style)

        QLabel_p("Current Word Exercise", "panelTitle")

        self.exercise_char = QLabel("—")
        self.exercise_char.setObjectName("characterDisplay")
        self.exercise_char.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(self.exercise_char)

        # Pinyin with tone marks per syllable
        self.exercise_pinyin = QLabel("Press 'New Exercise'")
        self.exercise_pinyin.setObjectName("pinyinLabel")
        self.exercise_pinyin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ll.addWidget(self.exercise_pinyin)

        self.exercise_meaning = QLabel("")
        self.exercise_meaning.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.exercise_meaning.setStyleSheet("color:#f0f3ff;font-size:16px; font-weight:600;")
        ll.addWidget(self.exercise_meaning)

        # Meaning language selector
        lang_row = QHBoxLayout()
        lang_lbl = QLabel("Meaning language")
        lang_lbl.setStyleSheet("color:#999;font-size:11px;")
        self.meaning_lang_combo = QComboBox()
        self.meaning_lang_combo.setObjectName("meaningLang")
        self.meaning_lang_combo.addItem("English", userData="en")
        self.meaning_lang_combo.addItem("Türkçe", userData="tr")
        self.meaning_lang_combo.addItem("Deutsch", userData="de")
        self.meaning_lang_combo.addItem("Русский", userData="ru")
        self.meaning_lang_combo.addItem("العربية", userData="ar")
        self.meaning_lang_combo.addItem("Español", userData="es")
        self.meaning_lang_combo.addItem("Français", userData="fr")
        self.meaning_lang_combo.currentIndexChanged.connect(self._on_meaning_language_changed)
        lang_row.addWidget(lang_lbl)
        lang_row.addStretch()
        lang_row.addWidget(self.meaning_lang_combo)
        ll.addLayout(lang_row)

        # Word-level tone breakdown (the key new UI element)
        self.tone_breakdown = QTextEdit()
        self.tone_breakdown.setReadOnly(True)
        self.tone_breakdown.setObjectName("feedbackBox")
        self.tone_breakdown.setMaximumHeight(160)
        self.tone_breakdown.setPlaceholderText("Tone breakdown per syllable will appear here...")
        ll.addWidget(self.tone_breakdown)

        # 2x2 button grid to free vertical space for meaning text
        btn_grid = QGridLayout()
        btn_grid.setHorizontalSpacing(8)
        btn_grid.setVerticalSpacing(8)

        btn_new = QPushButton("New Exercise")
        btn_new.setObjectName("primaryBtn")
        btn_new.clicked.connect(self._new_pronunciation_exercise)
        btn_grid.addWidget(btn_new, 0, 0)

        self.btn_listen_user = QPushButton("Listen")
        self.btn_listen_user.setObjectName("listenBtn")
        self.btn_listen_user.clicked.connect(self._play_user_recording)
        self.btn_listen_user.setEnabled(False)
        btn_grid.addWidget(self.btn_listen_user, 0, 1)

        self.record_btn = QPushButton("Record")
        self.record_btn.setObjectName("recordBtn")
        self.record_btn.clicked.connect(self._start_recording)
        btn_grid.addWidget(self.record_btn, 1, 0)

        self.btn_play_again = QPushButton("Play TTS")
        self.btn_play_again.setObjectName("playBtn")
        self.btn_play_again.clicked.connect(self._play_tts)
        self.btn_play_again.setEnabled(False)
        btn_grid.addWidget(self.btn_play_again, 1, 1)

        ll.addLayout(btn_grid)

        self.record_status = QLabel("")
        self.record_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.record_status.setStyleSheet("color:#72efdd;font-size:12px;")
        ll.addWidget(self.record_status)

        # Words-until-quiz counter
        self.quiz_counter_label = QLabel("")
        self.quiz_counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quiz_counter_label.setStyleSheet("color:#f4a261;font-size:11px;")
        ll.addWidget(self.quiz_counter_label)

        ll.addStretch()

        layout.addWidget(left)

        # ── Right: Results ──
        right = QFrame()
        right.setObjectName("panel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(18, 18, 18, 18)
        rl.setSpacing(10)

        self._ql(rl, "Analysis Results", "panelTitle")

        self.result_tone = QLabel("Detected Tone: —")
        self.result_tone.setObjectName("resultLabel")
        rl.addWidget(self.result_tone)

        self.result_accuracy_label = QLabel("Accuracy: —")
        self.result_accuracy_label.setObjectName("resultLabel")
        rl.addWidget(self.result_accuracy_label)

        self.accuracy_bar = QProgressBar()
        self.accuracy_bar.setObjectName("accuracyBar")
        self.accuracy_bar.setRange(0, 100)
        self.accuracy_bar.setValue(0)
        rl.addWidget(self.accuracy_bar)

        self.pitch_viz = PitchVisualizer()
        rl.addWidget(self.pitch_viz)

        # ── Collapsible Practice panel ──
        self.practice_toggle = QToolButton()
        self.practice_toggle.setObjectName("practiceToggle")
        self.practice_toggle.setText("Practice")
        self.practice_toggle.setCheckable(True)
        self.practice_toggle.setChecked(False)
        self.practice_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.practice_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.practice_toggle.clicked.connect(self._toggle_practice_popup)
        rl.addWidget(self.practice_toggle)

        # Popup container that overlays the panel (doesn't push layout down)
        self.practice_popup = QWidget(self)
        self.practice_popup.setObjectName("practicePopup")
        self.practice_popup.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.practice_popup.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        popup_layout = QVBoxLayout(self.practice_popup)
        popup_layout.setContentsMargins(10, 10, 10, 10)
        popup_layout.setSpacing(8)

        self.addon_tabs = QTabWidget()
        self.addon_tabs.setObjectName("addonTabs")
        # keep it compact to avoid pushing the tone reference off-screen
        self.addon_tabs.setMinimumHeight(220)
        self.addon_tabs.setMaximumHeight(320)
        self.addon_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        addon_tab = QWidget()
        addon_layout = QVBoxLayout(addon_tab)
        addon_layout.setContentsMargins(10, 10, 10, 10)
        addon_layout.setSpacing(8)

        self.practice_list = QListWidget()
        self.practice_list.setObjectName("practiceList")
        self.practice_list.setMinimumHeight(260)
        self.practice_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.practice_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.practice_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.practice_list.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.practice_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.practice_list.addItem(QListWidgetItem("Tones"))
        for i in range(1, 11):
            self.practice_list.addItem(QListWidgetItem(f"HSK{i}"))
        self.practice_list.currentItemChanged.connect(self._on_practice_selection_changed)
        addon_layout.addWidget(self.practice_list, 1)

        self.practice_hint = QLabel("Selected: Tones")
        self.practice_hint.setStyleSheet("color:#888;font-size:11px;")
        addon_layout.addWidget(self.practice_hint)

        self.addon_tabs.addTab(addon_tab, "Practice")
        popup_layout.addWidget(self.addon_tabs)

        self.practice_list.setCurrentRow(0)

        self._ql(rl, "Tone Shape Reference", "panelTitle")
        guide = QLabel(
            "Tone 1   ——   High Flat         (ma with overline)\n"
            "Tone 2   /      Rising              (ma with acute)\n"
            "Tone 3   V     Dipping-Rising   (ma with caron)\n"
            "Tone 4   \\     Falling             (ma with grave)\n"
            "Neutral   .     Short & light      (ma no mark)"
        )
        guide.setStyleSheet(
            "color:#ccc;font-size:13px;background:#0f0f1a;"
            "padding:12px;border-radius:6px;font-family:monospace;"
        )
        rl.addWidget(guide)
        rl.addStretch()

        layout.addWidget(right)

    # ─── Tab 2: Writing & Strokes ───

    def _build_writing_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # ── Left: Controls ──
        left = QFrame()
        left.setObjectName("panel")
        left.setMaximumWidth(290)
        self.drawing_canvas = DrawingCanvas()  # Initialize early to avoid AttributeError in buttons
        ll = QVBoxLayout(left)
        ll.setContentsMargins(18, 18, 18, 18)
        ll.setSpacing(10)

        self._ql(ll, "Select Character", "panelTitle")

        # ── Dictionary Search ──
        self.search_input = QLineEdit()
        self.search_input.setObjectName("searchInput")
        self.search_input.setPlaceholderText("Search English (e.g. cat)")
        self.search_input.textChanged.connect(self._on_search_input)
        ll.addWidget(self.search_input)

        self.search_results = QComboBox()
        self.search_results.setObjectName("searchResults")
        self.search_results.addItem("Results will appear here...")
        self.search_results.currentIndexChanged.connect(self._on_search_result_selected)
        ll.addWidget(self.search_results)

        # ── Direct Input ──
        self.char_input = QLineEdit()
        self.char_input.setObjectName("charInput")
        self.char_input.setMaxLength(1)
        self.char_input.setPlaceholderText("Type a character (e.g. 学)")
        self.char_input.textChanged.connect(self._on_char_input)
        ll.addWidget(self.char_input)

        self.stroke_info_label = QLabel("Strokes: —")
        self.stroke_info_label.setStyleSheet("color:#aaa;font-size:12px;")
        ll.addWidget(self.stroke_info_label)

        btn_ghost = QPushButton("Toggle Ghost Character")
        btn_ghost.setObjectName("secondaryBtn")
        btn_ghost.clicked.connect(self._toggle_ghost)
        ll.addWidget(btn_ghost)
        self._ghost_visible = True

        self.img_hint_btn = QPushButton("Toggle Image Mnemonic")
        self.img_hint_btn.setObjectName("secondaryBtn")
        self.img_hint_btn.clicked.connect(self._toggle_image_hint)
        ll.addWidget(self.img_hint_btn)

        btn_tutorial = QPushButton("Watch Tutorial (Animation)")
        btn_tutorial.setObjectName("primaryBtn")
        btn_tutorial.clicked.connect(self.drawing_canvas.start_tutorial)
        ll.addWidget(btn_tutorial)

        btn_ref = QPushButton("Toggle Reference Strokes")
        btn_ref.setObjectName("secondaryBtn")
        btn_ref.clicked.connect(self._toggle_reference)
        ll.addWidget(btn_ref)
        self._ref_visible = False

        btn_clear = QPushButton("Clear Canvas")
        btn_clear.setObjectName("secondaryBtn")
        btn_clear.clicked.connect(self._clear_canvas)
        ll.addWidget(btn_clear)

        btn_eval = QPushButton("Evaluate Writing")
        btn_eval.setObjectName("primaryBtn")
        btn_eval.setMinimumHeight(50)
        btn_eval.clicked.connect(self._evaluate_strokes)
        ll.addWidget(btn_eval)

        self.stroke_feedback = QTextEdit()
        self.stroke_feedback.setReadOnly(True)
        self.stroke_feedback.setObjectName("feedbackBox")
        self.stroke_feedback.setMaximumHeight(220)
        self.stroke_feedback.setPlaceholderText("Evaluation feedback will appear here...")
        ll.addWidget(self.stroke_feedback)
        ll.addStretch()

        # Initialize canvas with a default character
        self.char_input.setText("大")
        self._on_char_input("大")

        layout.addWidget(left)

        # ── Right: Canvas ──
        right = QFrame()
        right.setObjectName("panel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(18, 18, 18, 18)

        self._ql(rl, "Draw Here", "panelTitle")

        hint = QLabel("Draw strokes with your mouse. The ghost character is your guide.")
        hint.setStyleSheet("color:#666;font-size:12px;")
        rl.addWidget(hint)

        rl.addWidget(self.drawing_canvas)
        layout.addWidget(right)

        self.tabs.addTab(tab, "Writing & Strokes")

    # ─────────────────────────────────────────────────────────────
    # Reading Tab
    # ─────────────────────────────────────────────────────────────

    def _build_reading_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(20)

        # left: Story list
        left = QFrame()
        left.setObjectName("panel")
        left.setMaximumWidth(300)
        ll = QVBoxLayout(left)

        self._ql(ll, "Story Library", "panelTitle")

        self.stories = get_stories()

        self.story_list = QScrollArea()
        self.story_list_container = QWidget()
        self.story_list_layout = QVBoxLayout(self.story_list_container)
        self.story_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        for story in self.stories:
            btn = QPushButton(f"{story['title']}\n({story['title_zh']})")
            btn.setObjectName("storyBtn")
            btn.setMinimumHeight(60)
            btn.clicked.connect(lambda checked, s=story: self._load_story(s))
            self.story_list_layout.addWidget(btn)

        self.story_list.setWidget(self.story_list_container)
        self.story_list.setWidgetResizable(True)
        ll.addWidget(self.story_list)

        layout.addWidget(left)

        # right: Story Viewer
        right = QFrame()
        right.setObjectName("panel")
        rl = QVBoxLayout(right)

        self.story_title_label = QLabel("Select a story to begin")
        self.story_title_label.setObjectName("panelTitle")
        self.story_title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(self.story_title_label)

        self.story_content_area = QFrame()
        self.story_content_area.setMinimumHeight(400)
        self.scl = QVBoxLayout(self.story_content_area)
        self.scl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Story Illustration
        self.story_img = QLabel()
        self.story_img.setFixedSize(300, 200)
        self.story_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.story_img.setStyleSheet("background: #0a0a1f; border-radius: 10px; border: 1px solid #333;")
        self.scl.addWidget(self.story_img)
        self.scl.addSpacing(20)

        # We'll use a large font area for Chinese and Pinyin
        self.zh_label = QLabel("")
        self.zh_label.setStyleSheet("font-size: 40px; color: #fff; font-weight: bold;")
        self.zh_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zh_label.setWordWrap(True)

        self.py_label = QLabel("")
        self.py_label.setStyleSheet("font-size: 20px; color: #ffea00; font-family: 'Consolas';")
        self.py_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.en_label = QLabel("")
        self.en_label.setStyleSheet("font-size: 16px; color: #aaa; font-style: italic;")
        self.en_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.en_label.setWordWrap(True)

        self.scl.addWidget(self.py_label)
        self.scl.addWidget(self.zh_label)
        self.scl.addSpacing(10)
        self.scl.addWidget(self.en_label)

        rl.addWidget(self.story_content_area)

        # Navigation
        nav = QHBoxLayout()
        self.btn_prev_page = QPushButton("◀ Önceki")
        self.btn_prev_page.clicked.connect(self._prev_page)
        self.btn_prev_page.setEnabled(False)

        self.btn_read_aloud = QPushButton("🔊 Sesli Oku")
        self.btn_read_aloud.setObjectName("primaryBtn")
        self.btn_read_aloud.clicked.connect(self._read_story_page)

        self.btn_replay_story = QPushButton("🔁 Tekrar")
        self.btn_replay_story.setObjectName("secondaryBtn")
        self.btn_replay_story.clicked.connect(self._read_story_page)
        self.btn_replay_story.setEnabled(False)

        self.btn_next_page = QPushButton("Sonraki ▶")
        self.btn_next_page.clicked.connect(self._next_page)
        self.btn_next_page.setEnabled(False)

        nav.addWidget(self.btn_prev_page)
        nav.addStretch()
        nav.addWidget(self.btn_read_aloud)
        nav.addWidget(self.btn_replay_story)
        nav.addStretch()
        nav.addWidget(self.btn_next_page)
        rl.addLayout(nav)

        self.page_indicator = QLabel("Page 0 / 0")
        self.page_indicator.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_indicator.setStyleSheet("color: #666;")
        rl.addWidget(self.page_indicator)

        layout.addWidget(right)
        self.tabs.addTab(tab, "Reading & Stories")

    def _load_story(self, story):
        self.current_story = story
        self.current_page_idx = 0
        self.story_title_label.setText(f"{story['title']} - {story['title_zh']}")
        self._update_story_view()
        # Auto-play first page when a story is selected
        QTimer.singleShot(400, self._read_story_page)

    def _update_story_view(self):
        if not self.current_story:
            return
        page = self.current_story['pages'][self.current_page_idx]
        self.zh_label.setText(page['zh'])
        self.py_label.setText(page['py'])
        self.en_label.setText(page['en'])

        # Enable replay once a story is loaded
        self.btn_replay_story.setEnabled(True)

        # Show illustration
        img_path = page.get('illustration', "")
        if img_path:
            base_dir = Path(__file__).resolve().parent.parent
            abs_path = str(base_dir / img_path.replace("/", os.sep))
            if os.path.exists(abs_path):
                pix = QPixmap(abs_path).scaled(300, 200, Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
                self._set_story_image(pix)
            else:
                self._set_story_image(self._build_story_fallback_pixmap(page))
        else:
            self._set_story_image(self._build_story_fallback_pixmap(page))

        count = len(self.current_story['pages'])
        self.page_indicator.setText(f"Sayfa {self.current_page_idx + 1} / {count}")
        self.btn_prev_page.setEnabled(self.current_page_idx > 0)
        self.btn_next_page.setEnabled(self.current_page_idx < count - 1)

    def _set_story_image(self, pix: QPixmap):
        """Always render story visuals as image (no text placeholders)."""
        self.story_img.setText("")
        self.story_img.setStyleSheet("background: #0a0a1f; border-radius: 10px; border: 1px solid #333;")
        self.story_img.setPixmap(pix)

    def _build_story_fallback_pixmap(self, page: dict) -> QPixmap:
        """
        Builds a deterministic illustration card when image files are missing.
        This removes text placeholders and always shows a visual scene.
        """
        w, h = 300, 200
        pix = QPixmap(w, h)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        en = str(page.get("en", "")).lower()
        zh = str(page.get("zh", ""))

        # Background gradient
        top = QColor("#17345e")
        bottom = QColor("#0b1b33")
        if "sun" in en or "morning" in en or "day" in en:
            top = QColor("#2f6db2")
            bottom = QColor("#3f9b6c")
        elif "night" in en:
            top = QColor("#10152b")
            bottom = QColor("#1a2448")
        elif "mountain" in en or "tree" in en or "garden" in en:
            top = QColor("#1f4b7a")
            bottom = QColor("#2b6a43")

        painter.fillRect(0, 0, w, h, bottom)
        for y in range(h):
            t = y / max(1, h - 1)
            r = int(top.red() * (1 - t) + bottom.red() * t)
            g = int(top.green() * (1 - t) + bottom.green() * t)
            b = int(top.blue() * (1 - t) + bottom.blue() * t)
            painter.setPen(QColor(r, g, b))
            painter.drawLine(0, y, w, y)

        # Simple landscape layers
        painter.setBrush(QColor(24, 44, 74, 180))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(-30, 120, 180, 90)
        painter.drawEllipse(120, 110, 200, 100)

        # Sun/moon hint
        painter.setBrush(QColor(255, 236, 140, 220))
        painter.drawEllipse(220, 20, 48, 48)

        # Chinese scene caption (short)
        painter.setPen(QColor("#f7f7f7"))
        font = QFont("Microsoft YaHei UI", 18)
        font.setBold(True)
        painter.setFont(font)
        scene_text = zh[:10] + ("..." if len(zh) > 10 else "")
        painter.drawText(16, 38, scene_text)

        painter.end()
        return pix

    def _next_page(self):
        if self.current_story and self.current_page_idx < len(self.current_story['pages']) - 1:
            self.current_page_idx += 1
            self._update_story_view()
            # Auto-play the new page
            QTimer.singleShot(300, self._read_story_page)

    def _prev_page(self):
        if self.current_story and self.current_page_idx > 0:
            self.current_page_idx -= 1
            self._update_story_view()
            # Auto-play the new page
            QTimer.singleShot(300, self._read_story_page)

    def _read_story_page(self):
        if not self.current_story:
            return
        page = self.current_story['pages'][self.current_page_idx]
        # Use speak_async so the UI never freezes and the TTS queue is flushed
        # before each new utterance, ensuring every page plays reliably.
        self.tts.speak_async(page['zh'])
        # Animation: slightly highlight text during reading
        self.zh_label.setStyleSheet("font-size: 40px; color: #ffea00; font-weight: bold;")
        QTimer.singleShot(2000, lambda: self.zh_label.setStyleSheet("font-size: 40px; color: #fff; font-weight: bold;"))

    # ─── Tab 3: AI Tutor ───

    def _build_tutor_tab(self):
        tab = QWidget()
        self.tabs.addTab(tab, "AI Tutor")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self._ql(layout, "AI Tutor Chat", "panelTitle")

        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setObjectName("chatDisplay")
        layout.addWidget(self.chat_display)

        input_row = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setObjectName("chatInput")
        self.chat_input.setPlaceholderText("Ask your tutor anything about Mandarin...")
        self.chat_input.returnPressed.connect(self._send_chat)
        input_row.addWidget(self.chat_input)

        send_btn = QPushButton("Send")
        send_btn.setObjectName("primaryBtn")
        send_btn.setFixedWidth(80)
        send_btn.clicked.connect(self._send_chat)
        input_row.addWidget(send_btn)
        layout.addLayout(input_row)

        progress_btn = QPushButton("Show Progress Summary")
        progress_btn.setObjectName("secondaryBtn")
        progress_btn.clicked.connect(self._show_progress)
        layout.addWidget(progress_btn)

    # ─────────────────────────────────────────────
    # Helper
    # ─────────────────────────────────────────────

    def _ql(self, layout, text, obj=None, style=None):
        lbl = QLabel(text)
        if obj:
            lbl.setObjectName(obj)
        if style:
            lbl.setStyleSheet(style)
        layout.addWidget(lbl)
        return lbl

    def _refresh_header(self):
        lvl = self.progress.get_level_info()
        nxt = self.progress.get_next_level_info()
        pct = int(self.progress.get_xp_progress_pct() * 100)
        self.level_label.setText(f"Level {lvl['level']} — {lvl['name']}")
        self.xp_bar.setValue(pct)
        nxt_xp = nxt["xp_required"] if nxt else "MAX"
        self.xp_label.setText(f"{self.progress.xp} XP / {nxt_xp}")

        words_left = 5 - self.progress.words_since_last_quiz
        self.quiz_counter_label.setText(f"Quiz in {words_left} correct word(s)")

    # ─────────────────────────────────────────────
    # Pronunciation Tab Logic
    # ─────────────────────────────────────────────

    def _new_pronunciation_exercise(self):
        vocab = self._get_selected_vocab()
        import random
        word = random.choice(vocab)
        self.current_exercise = word

        self.exercise_char.setText(word["character"])
        self.exercise_pinyin.setText(word["pinyin"])
        self._meaning_src_text = str(word.get("meaning", ""))
        self._update_meaning_label()

        # ── Word-level tone breakdown ──
        self._build_tone_breakdown(word)

        # Reset result area
        self.record_status.setText("")
        self.result_tone.setText("Detected Tone: —")
        self.result_accuracy_label.setText("Accuracy: —")
        self.accuracy_bar.setValue(0)
        self.pitch_viz.f0_data = None
        self.pitch_viz.update()

        # Activate Play Again button now that we have an exercise
        self.btn_play_again.setEnabled(True)

        # Play TTS automatically for the new word
        self._play_tts()

    def _on_meaning_language_changed(self, idx: int):
        self._update_meaning_label()

    def _update_meaning_label(self):
        src = (self._meaning_src_text or "").strip()
        if not src:
            self.exercise_meaning.setText("")
            return

        lang = self.meaning_lang_combo.currentData() if hasattr(self, "meaning_lang_combo") else "en"
        if lang is None:
            lang = "en"
        lang = str(lang)

        if lang == "en":
            self.exercise_meaning.setText(f"Meaning: {src}")
            return

        cache_key = (src, lang)
        if cache_key in self._meaning_translation_cache:
            self.exercise_meaning.setText(self._meaning_translation_cache[cache_key])
            return

        self.exercise_meaning.setText("Meaning: …")

        def _do_translate():
            translated = self._translate_meaning(src, lang)
            text = f"Meaning: {translated}" if translated else f"Meaning: {src}"
            self._meaning_translation_cache[cache_key] = text
            QTimer.singleShot(0, lambda: self.exercise_meaning.setText(text))

        threading.Thread(target=_do_translate, daemon=True).start()

    def _translate_meaning(self, text: str, lang: str) -> str:
        """
        Translates the short English gloss into the selected UI language.
        Provider selection via env TRANSLATION_PROVIDER:
          - 'openai'
          - 'deepl'
          - 'auto' (default): openai -> deepl -> original text
        """
        provider = str(os.environ.get("TRANSLATION_PROVIDER", "auto")).strip().lower()

        if provider == "openai":
            return self._translate_with_openai(text, lang)
        if provider == "deepl":
            return self._translate_with_deepl(text, lang)

        # auto
        out = self._translate_with_openai(text, lang)
        if out != text:
            return out
        out = self._translate_with_deepl(text, lang)
        return out

    def _translate_with_openai(self, text: str, lang: str) -> str:
        if not getattr(self.tutor, "use_real_ai", False):
            return text
        try:
            from openai import OpenAI
            client = OpenAI(
                api_key=getattr(self.tutor, "api_key", None),
                base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
            )
            lang_names = {
                "tr": "Turkish",
                "de": "German",
                "ru": "Russian",
                "ar": "Arabic",
                "es": "Spanish",
                "fr": "French",
            }
            target = lang_names.get(lang, "English")
            system = (
                "You are a translation engine for short vocabulary glosses. "
                "Translate to the target language. Output only the translation."
            )
            prompt = f"Target language: {target}\nText: {text}"
            resp = client.chat.completions.create(
                model=os.environ.get("AI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=60,
            )
            out = (resp.choices[0].message.content or "").strip()
            return out or text
        except Exception:
            return text

    def _translate_with_deepl(self, text: str, lang: str) -> str:
        key = os.environ.get("DEEPL_API_KEY")
        if not key:
            return text
        target_map = {
            "en": "EN",
            "tr": "TR",
            "de": "DE",
            "ru": "RU",
            "ar": "AR",
            "es": "ES",
            "fr": "FR",
        }
        target = target_map.get(lang, "EN")
        try:
            endpoint = os.environ.get("DEEPL_API_URL", "https://api-free.deepl.com/v2/translate")
            payload = urlencode({
                "auth_key": key,
                "text": text,
                "target_lang": target,
                "source_lang": "EN"
            }).encode("utf-8")
            req = Request(endpoint, data=payload, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urlopen(req, timeout=10) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            import json
            data = json.loads(body)
            arr = data.get("translations", [])
            if arr and isinstance(arr, list):
                out = str(arr[0].get("text", "")).strip()
                return out or text
            return text
        except Exception:
            return text

    def _build_tone_breakdown(self, word: dict):
        """
        Builds a rich per-syllable tone explanation for the whole word.
        Shows each character + its pinyin syllable + tone description in context.
        """
        chars = list(word["character"])
        pinyin_parts = word["pinyin"].split()
        tones = word.get("tones", [])

        lines = [f'Word: {word["character"]}  ({word["pinyin"]})  = {word["meaning"]}\n']
        lines.append("Syllable-by-syllable tone guide:\n")

        for i, tone_num in enumerate(tones):
            char = chars[i] if i < len(chars) else "?"
            pin = pinyin_parts[i] if i < len(pinyin_parts) else "?"
            info = get_tone_info(tone_num)
            tone_shape = {
                1: "——   (flat high)",
                2: "/     (rising)",
                3: "V    (dip then rise)",
                4: "\\    (falling)",
                5: "·    (short, neutral)",
            }.get(tone_num, "?")
            lines.append(
                f"  Syllable {i + 1}: '{char}' ({pin})\n"
                f"    Tone: {info['name']}\n"
                f"    Shape: {tone_shape}\n"
                f"    Tip: {info['description']}\n"
                f"    Example word: {info['example_pinyin']} ({info['example_character']}) = {info['example_meaning']}\n"
            )

        self.tone_breakdown.setPlainText("".join(lines))

    def _play_tts(self):
        if self.current_exercise:
            self.tts.speak_async(self.current_exercise["character"])

    def _play_user_recording(self):
        if not self.last_user_wav_path:
            self.record_status.setText("No recording yet. Use 'Record & Analyze' first.")
            return

        self._player.setSource(QUrl.fromLocalFile(self.last_user_wav_path))
        self._player.play()
        self.record_status.setText("Playing your last recording.")

    def _on_practice_selection_changed(self, current, previous):
        if current is None:
            return
        text = current.text().strip()
        if text.lower() == "tones":
            self.practice_mode = "tones"
        elif text.upper().startswith("HSK"):
            self.practice_mode = text.lower()
        else:
            self.practice_mode = "tones"
        self.practice_hint.setText(f"Selected: {text}")
        self.practice_toggle.setText(f"Practice: {text}")
        # Small visible confirmation without requiring console access
        try:
            vocab = self._get_selected_vocab()
            self.record_status.setText(f"Practice set to {text} ({len(vocab)} word(s)).")
        except Exception:
            pass

    def _toggle_practice_popup(self):
        expanded = bool(self.practice_toggle.isChecked())
        if not expanded:
            self.practice_popup.hide()
            self.practice_toggle.setArrowType(Qt.ArrowType.RightArrow)
            return

        # Position popup under the toggle button (overlaying content below)
        btn_global = self.practice_toggle.mapToGlobal(self.practice_toggle.rect().bottomLeft())
        width = max(320, self.practice_toggle.width())
        height = min(380, max(260, self.addon_tabs.sizeHint().height() + 40))
        self.practice_popup.setFixedSize(width, height)
        self.practice_popup.move(btn_global)
        self.practice_popup.show()
        self.practice_toggle.setArrowType(Qt.ArrowType.DownArrow)

    def _get_selected_vocab(self) -> list:
        """
        Returns the active vocabulary pool based on the Practice selector.

        - Tones: uses tone drills (mā/má/mǎ/mà/ma) instead of advanced words
        - HSK1..HSK10: uses res/data/hsk_vocab.json (utils.hsk_vocab)
          If a selected HSK level is empty/missing, falls back to the progress pool.
        """
        mode = (self.practice_mode or "tones").lower()
        if mode == "tones":
            return self._get_tone_drills()

        if mode.startswith("hsk"):
            try:
                n = int(mode.replace("hsk", ""))
            except Exception:
                n = 1
            hsk_vocab = get_hsk_vocabulary(n)
            if hsk_vocab:
                return hsk_vocab
            return get_vocabulary(self.progress.get_vocab_level())

        return get_vocabulary(self.progress.get_vocab_level())

    def _get_tone_drills(self) -> list[dict]:
        """
        Builds a small, stable practice set for pure tone training.

        Uses the examples already defined in utils.pinyin_utils.get_tone_info:
        mā / má / mǎ / mà / ma
        """
        drills: list[dict] = []
        for tone_num in [1, 2, 3, 4, 5]:
            info = get_tone_info(tone_num)
            drills.append({
                "character": info.get("example_character", "—"),
                "pinyin": info.get("example_pinyin", ""),
                "meaning": info.get("example_meaning", "Tone drill"),
                "tones": [tone_num],
            })
        return drills

    def _start_recording(self):
        if not self.current_exercise:
            self.record_status.setText("Pick a word first!")
            return
        self.record_btn.setEnabled(False)
        self.record_btn.setText("Recording...")
        self.record_status.setText("Recording... speak now!")
        self.recording_worker = RecordingWorker(self.analyzer)
        self.recording_worker.result_ready.connect(self._on_recording_done)
        self.recording_worker.start()

    def _on_recording_done(self, result: dict):
        self.record_btn.setEnabled(True)
        self.record_btn.setText("Record")

        detected_tone = result["tone"]
        accuracy = result["accuracy"]

        self.result_tone.setText(f"Detected Tone: {result['tone_name']}")
        self.result_accuracy_label.setText(f"Accuracy: {accuracy:.0%}")
        self.accuracy_bar.setValue(int(accuracy * 100))
        self.pitch_viz.set_data(result["f0"], detected_tone)

        curr_ex = self.current_exercise or {}
        expected_tones = curr_ex.get("tones", [])
        expected = expected_tones[0] if expected_tones else None
        # Update progress tracker
        quiz_triggered = self.progress.record_pronunciation_attempt(accuracy)
        self._refresh_header()

        # AI feedback
        context = {
            "detected_tone": detected_tone,
            "expected_tone": expected,
            "accuracy": accuracy,
            "character": curr_ex.get("character", ""),
            "word_pinyin": curr_ex.get("pinyin", ""),
            "word_meaning": curr_ex.get("meaning", ""),
        }
        feedback = self.tutor.generate_response("pronunciation result", context)
        self._append_chat("Tutor", feedback)
        self.record_status.setText("Analysis complete! Check the AI Tutor tab for feedback.")

        # Save the recorded audio (from the existing recording mechanic) for playback
        try:
            out_dir = get_appdata_dir() / "audio" / "user_recordings"
            out_dir.mkdir(parents=True, exist_ok=True)
            import time
            wav_path = str(out_dir / f"user_{int(time.time() * 1000)}.wav")
            self.last_user_wav_path = self.analyzer.save_last_recording_to_wav(wav_path)
            self.btn_listen_user.setEnabled(True)
        except Exception:
            # If saving fails, keep the UI responsive; analysis results still work.
            self.last_user_wav_path = None
            self.btn_listen_user.setEnabled(False)

        # Trigger quiz if due
        if quiz_triggered:
            QTimer.singleShot(800, self._launch_quiz)
        elif accuracy >= 0.90:
            # Auto-progression: move to next word if accuracy is high
            self.record_status.setText("Excellent! Loading next word...")
            QTimer.singleShot(1500, self._new_pronunciation_exercise)

    # ─────────────────────────────────────────────
    # Quiz Logic
    # ─────────────────────────────────────────────

    def _launch_quiz(self):
        vocab_level = self.progress.get_vocab_level()
        all_vocab = get_vocabulary(vocab_level)
        self.quiz_gen = QuizGenerator(all_vocab)
        questions = self.quiz_gen.generate_quiz(5)
        dialog = QuizDialog(questions, self.progress, parent=self)
        dialog.exec()
        self.progress.clear_quiz_pending()
        self._refresh_header()
        self._append_chat("System", f"Quiz complete! {self.progress.get_summary_text()}")

    # ─────────────────────────────────────────────
    # Writing Tab Logic
    # ─────────────────────────────────────────────

    def _on_search_input(self, text: str):
        results = search_dictionary(text)
        self.search_results.blockSignals(True)
        self.search_results.clear()

        if not results:
            self.search_results.addItem("No results found.")
        else:
            self.search_results.addItem(f"Found {len(results)} results...")
            for r in results:
                char = r.get("character", "")
                py_list = r.get("pinyin", [])
                py_str = py_list[0] if py_list else ""
                defi = r.get("definition", "")
                if len(defi) > 40:
                    defi = defi[:37] + "..."
                display_text = f"{char} ({py_str}) - {defi}"
                self.search_results.addItem(display_text, userData=char)

        self.search_results.blockSignals(False)

    def _on_search_result_selected(self, index: int):
        if index <= 0:
            return
        char = self.search_results.itemData(index)
        if char:
            self.char_input.setText(char)

    def _on_char_input(self, char: str):
        if not char:
            return

        strokes = get_stroke_data(char)
        if not strokes:
            self.stroke_info_label.setText("Strokes: Not found in DB")
            self.drawing_canvas.clear()
            self.drawing_canvas.set_ghost_character(char)
            self.drawing_canvas.set_reference_strokes([], show=False)
            self.drawing_canvas.set_background_image("")
            return

        self.stroke_info_label.setText(f"Strokes: {len(strokes)}")
        self.drawing_canvas.clear()
        self.drawing_canvas.set_ghost_character(char)
        self.drawing_canvas.set_reference_strokes(strokes, show=self._ref_visible)
        self.stroke_feedback.clear()
        self._ghost_visible = True

        # Load mnemonic image if available
        mnemonic_map = {
            "一": "res/img/one.png",
            "二": "res/img/two.png",
            "三": "res/img/three.png",
            "人": "res/img/person.png",
            "大": "res/img/big.png",
            "山": "res/img/mountain.png",
            "口": "res/img/mouth.png",
            "水": "res/img/water.png",
        }
        img_rel_path = mnemonic_map.get(char, "")
        if img_rel_path:
            abs_path = resource_path(img_rel_path.replace("/", os.sep))
            self.drawing_canvas.set_background_image(abs_path)
        else:
            self.drawing_canvas.set_background_image("")

    def _toggle_image_hint(self):
        self.drawing_canvas.show_image_hint = not self.drawing_canvas.show_image_hint
        print(f"[UI] Toggle Image Mnemonic. Now: {self.drawing_canvas.show_image_hint}")
        self.drawing_canvas.update()

    def _toggle_ghost(self):
        self._ghost_visible = not self._ghost_visible
        char = self.char_input.text() if self._ghost_visible else ""
        self.drawing_canvas.set_ghost_character(char)

    def _toggle_reference(self):
        self._ref_visible = not self._ref_visible
        char = self.char_input.text()
        strokes = get_stroke_data(char)
        self.drawing_canvas.set_reference_strokes(strokes, show=self._ref_visible)

    def _clear_canvas(self):
        self.drawing_canvas.clear()
        # Keep ghost and reference state as-is
        self.stroke_feedback.clear()

    def _evaluate_strokes(self):
        char = self.char_input.text().strip()
        if not char:
            return
        user_strokes = self.drawing_canvas.get_normalized_strokes()
        result = self.evaluator.evaluate(char, user_strokes)
        self.stroke_feedback.setPlainText(result["feedback"])
        self.progress.record_writing_attempt(result["score"])
        self._refresh_header()

        if result["score"] >= 0.90:
            self.stroke_feedback.append("\nExcellent! Great job on this character!")

    # ─────────────────────────────────────────────
    # AI Tutor Chat Logic
    # ─────────────────────────────────────────────

    def _send_welcome(self):
        welcome = self.tutor.generate_response("hello", {})
        self._append_chat("Tutor", welcome)

    def _send_chat(self):
        text = self.chat_input.text().strip()
        if not text:
            return
        self.chat_input.clear()
        self._append_chat("You", text)
        self._append_chat("Tutor", "Thinking...")

        def _call():
            resp = self.tutor.generate_response(text, {})
            self._replace_last_tutor_message(resp)
        threading.Thread(target=_call, daemon=True).start()

    def _show_progress(self):
        summary = self.progress.get_summary_text()
        self._append_chat("Progress", summary)

    def _append_chat(self, sender: str, message: str):
        current = self.chat_display.toPlainText()
        sep = "\n" + "-" * 48 + "\n" if current else ""
        self.chat_display.setPlainText(current + sep + f"{sender}:\n{message}\n")
        sb = self.chat_display.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    def _replace_last_tutor_message(self, new_message: str):
        current = self.chat_display.toPlainText()
        placeholder = "Tutor:\nThinking..."
        if placeholder in current:
            idx = current.rfind(placeholder)
            updated = current[:idx] + f"Tutor:\n{new_message}" + current[idx + len(placeholder):]
            self.chat_display.setPlainText(updated)
        else:
            self._append_chat("Tutor", new_message)
        sb = self.chat_display.verticalScrollBar()
        if sb:
            sb.setValue(sb.maximum())

    # ─────────────────────────────────────────────
    # Stylesheet
    # ─────────────────────────────────────────────

    def _apply_stylesheet(self):
        self.setStyleSheet("""
            QMainWindow { background: #0b1220; }
            QWidget { background: #0b1220; color: #e8eefc;
                      font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; }
            #header {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #0b1220, stop:1 #0a1a2f);
                border-bottom: 1px solid #1f2a44;
            }
            #appTitle { font-size: 20px; font-weight: bold; color: #4aa3ff; }
            #levelDisplay { color: #22c55e; font-weight: bold; font-size: 14px; }
            QProgressBar#xpBar {
                background: #0b1020; border-radius: 5px; border: none;
            }
            QProgressBar#xpBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #4aa3ff, stop:1 #22c55e);
                border-radius: 5px;
            }
            QTabWidget#mainTabs::pane { border: none; background: #0b1220; }
            QTabBar::tab { background: #0f172a; color: #9ca3af; padding: 10px 22px;
                           font-size: 13px; border-bottom: 2px solid transparent; }
            QTabBar::tab:selected { color: #4aa3ff; border-bottom: 2px solid #4aa3ff;
                                    background: #0b1220; }
            QTabBar::tab:hover { color: #e8eefc; background: #0f172a; }
            QTabWidget#addonTabs::pane { border: none; background: transparent; }
            QTabWidget#addonTabs QTabBar::tab { padding: 6px 12px; font-size: 12px; }
            QToolButton#practiceToggle {
                background: #0f172a;
                color: #4aa3ff;
                border: 1px solid #1f2a44;
                border-radius: 8px;
                padding: 8px 10px;
                font-weight: bold;
                text-align: left;
            }
            QToolButton#practiceToggle:hover { border-color: #4aa3ff; }
            QWidget#practicePopup {
                background: #0f172a;
                border: 1px solid #1f2a44;
                border-radius: 10px;
            }
            QComboBox#meaningLang {
                background: #0b1020;
                border: 1px solid #1f2a44;
                border-radius: 8px;
                padding: 6px 10px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QComboBox#meaningLang:hover { border-color: #4aa3ff; }
            QComboBox#meaningLang QAbstractItemView { background: #0f172a; color: #eee; }
            #panel { background: #0f172a; border-radius: 12px; border: 1px solid #1f2a44; }
            QListWidget#practiceList {
                background: #0b1020;
                border: 1px solid #1f2a44;
                border-radius: 8px;
                padding: 6px;
                color: #e0e0e0;
            }
            QListWidget#practiceList::item {
                padding: 8px 10px;
                margin: 2px 0px;
                border-radius: 6px;
            }
            QListWidget#practiceList::item:selected {
                background: #0f172a;
                color: #4aa3ff;
                border: 1px solid #4aa3ff;
            }
            #storyBtn {
        background-color: #0f172a;
        border: 1px solid #1f2a44;
        border-radius: 8px;
        padding: 5px;
        color: #eee;
        text-align: center;
        margin-bottom: 5px;
    }
    #storyBtn:hover {
        border-color: #4aa3ff;
    }
    #storyBtn:pressed {
        background-color: #0b1020;
    }
    #panelTitle { font-size: 15px; font-weight: bold; color: #4aa3ff; margin-bottom: 4px; }
            #characterDisplay { font-size: 72px; color: #fff; padding: 8px;
                                background: #0b1020; border-radius: 8px; border: 1px solid #1f2a44; }
            #pinyinLabel { font-size: 22px; color: #22c55e; font-weight: bold; }
            #primaryBtn {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #2b84d4, stop:1 #1a9e47);
                color: #fff; border: none; border-radius: 8px;
                padding: 10px; font-size: 14px; font-weight: bold;
            }
            #primaryBtn:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #1a6ab3, stop:1 #137d35); }
            #primaryBtn:disabled { background: #1f2a44; color: #666; }
            #secondaryBtn { background: #0f172a; color: #4aa3ff; border: 1px solid #1f2a44;
                            border-radius: 8px; padding: 8px; font-size: 13px; }
            #secondaryBtn:hover { border-color: #4aa3ff; }
            #listenBtn {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #ea580c, stop:1 #f59e0b);
                color: #ffffff; border: none; border-radius: 8px;
                padding: 8px; font-size: 13px; font-weight: bold;
            }
            #listenBtn:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #c2410c, stop:1 #d97706);
            }
            #playBtn {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #16a34a, stop:1 #22c55e);
                color: #ffffff; border: none; border-radius: 8px;
                padding: 8px; font-size: 13px; font-weight: bold;
            }
            #playBtn:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #15803d, stop:1 #16a34a);
            }
            #recordBtn {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #831843, stop:1 #c01050);
                color: #fff; border: none; border-radius: 8px;
                padding: 10px; font-size: 14px; font-weight: bold;
            }
            #recordBtn:hover { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                stop:0 #a02050, stop:1 #e01565); }
            #recordBtn:disabled { background: #441122; color: #888; }
            #resultLabel { font-size: 14px; color: #22c55e; padding: 4px; }
            QProgressBar#accuracyBar { background: #0b1020; border-radius: 6px;
                border: 1px solid #1f2a44; height: 14px; text-align: center; color: #fff; }
            QProgressBar#accuracyBar::chunk {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #4aa3ff, stop:1 #22c55e);
                border-radius: 6px;
            }
            QTextEdit#chatDisplay { background: #0b1020; border: 1px solid #1f2a44;
                border-radius: 8px; padding: 12px; color: #ddd; font-size: 13px; }
            QTextEdit#feedbackBox { background: #0b1020; border: 1px solid #1f2a44;
                border-radius: 8px; padding: 8px; color: #ccc; font-size: 12px; }
            QLineEdit#chatInput { background: #0b1020; border: 1px solid #1f2a44;
                border-radius: 8px; padding: 10px; color: #eee; font-size: 13px; }
            QLineEdit#chatInput:focus { border: 1px solid #4aa3ff; }
            QComboBox#charCombo { background: #0b1020; border: 1px solid #1f2a44;
                border-radius: 8px; padding: 8px; color: #eee; font-size: 18px; }
            QComboBox QAbstractItemView { background: #0f172a;
                selection-background-color: #4aa3ff; color: #eee; }
            QScrollBar:vertical { background: #0b1020; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #4aa3ff; border-radius: 4px; }
        """)
