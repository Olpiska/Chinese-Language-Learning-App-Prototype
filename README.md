# 🐼 Mandarin Learning Application

A comprehensive, desktop-based Mandarin Chinese learning application built with **Python** and **PyQt6**.

---

## ✨ Features

- **Interactive Writing Practice**  
  Learn strokes and characters with mnemonic hints.

- **Gamified Progression System**  
  Earn XP, level up, and stay motivated to learn daily.

- **AI-Powered Tutor**  
  Get instant feedback and dynamic lessons from an integrated AI tutor.

- **Reading Module**  
  Read stories tailored for language learners with built-in Pinyin support.

- **Text-To-Speech (TTS)**  
  Robust, non-blocking audio playback for pronunciation and story reading to improve listening skills.

- **Background Reminders**  
  System tray integration optionally reminds you to practice daily.

---

## 🛠 Technologies Used

- **Python 3.10+**
- **PyQt6** for a modern, responsive user interface
- **SAPI5 (Windows)** for Text-to-Speech generation

---

## 🚀 Installation and Execution

1. **Prerequisites**  
   Ensure Python is installed.

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run Application**
   ```bash
   python main.py
   ```

4. **Standalone Options**  
   The application can also be packaged into a standalone Windows `.exe` using the `build_exe.py` script.

---

## 🤝 Contributing

Make sure to run static analysis tools to maintain the highest code quality standards:

```bash
flake8
mypy
```

The application enforces zero linting and type-checking errors.
