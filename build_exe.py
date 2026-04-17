import os
import sys
import subprocess
from pathlib import Path

def build():
    print("Installing PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    
    print("Building Executable...")
    base_dir = Path(__file__).resolve().parent
    main_script = base_dir / "main.py"
    res_dir = base_dir / "res"
    
    # We include res/ directory inside the resulting Pyinstaller package.
    # On Windows, PyInstaller separator is ';'
    res_path = f"{res_dir};res/"
    
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed", # Don't open console by default
        f"--add-data={res_path}",
        "--name=ChinaLearningApp",
        str(main_script)
    ]
    
    subprocess.check_call(cmd, cwd=str(base_dir))
    
    print("Build Complete! The .exe is located in the 'dist/ChinaLearningApp' folder.")

if __name__ == "__main__":
    build()
