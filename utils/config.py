import os
import sys
import json
from pathlib import Path

def get_appdata_dir() -> Path:
    """Returns the user-specific AppData directory for saving progress and settings."""
    appdata = os.getenv('APPDATA')
    if appdata:
         base = Path(appdata) / "ChinaLearningApp"
    else:
         base = Path.home() / ".chinalearningapp"
    base.mkdir(parents=True, exist_ok=True)
    return base

def get_base_dir() -> Path:
    """Returns the directory of the executable or the source root."""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def resource_path(relative_path: str) -> str:
    """ 
    Get absolute path to resource, works for dev and for PyInstaller.
    Used for reading assets, images, read-only data files.
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class SettingsManager:
    def __init__(self):
        self.filepath = get_appdata_dir() / "settings.json"
        
        # Default settings
        self.settings = {
            "reminder_enabled": True,
            "reminder_type": "hours_after", # 'hours_after' or 'time_of_day' or 'no_xp_today'
            "reminder_value": "3",          # "3" (hours) or "19:00"
            "close_action": "ask"           # 'ask', 'tray', 'quit'
        }
        self.load()

    def load(self):
        if self.filepath.exists():
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.settings.update(data)
            except Exception:
                pass
    
    def save(self):
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass

    def get(self, key):
        return self.settings.get(key)

    def set(self, key, value):
        self.settings[key] = value
        self.save()

SETTINGS = SettingsManager()
