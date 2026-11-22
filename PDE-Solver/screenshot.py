"""Скриншот работающего стенда для README и титульного слайда.

1. Запустите стенд: python app.py
2. В другом окне терминала: python screenshot.py [ширина высота [файл]]
   По умолчанию 1920 × 1080 → figures/app.png.

Нужен Google Chrome, Chromium или Microsoft Edge. Путь находится автоматически
для Windows, macOS и Linux; другой путь можно задать переменной окружения CHROME.
"""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).parent
URL = "http://127.0.0.1:8050/"

CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]


def find_browser():
    if os.environ.get("CHROME"):
        return os.environ["CHROME"]
    for path in CANDIDATES:
        if Path(path).exists():
            return path
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge"):
        if shutil.which(name):
            return shutil.which(name)
    sys.exit("Не найден Chrome/Chromium/Edge: укажите путь в переменной окружения CHROME.")


def shoot(out, width=1920, height=1080):
    """Снимок страницы в безголовом браузере; WebGL для 3D — через SwiftShader."""
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([
            find_browser(), "--headless=new", f"--user-data-dir={profile}", "--hide-scrollbars",
            f"--window-size={width},{height}", "--force-device-scale-factor=1",
            "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist",
            "--virtual-time-budget=25000", "--run-all-compositor-stages-before-draw",
            f"--screenshot={out}", URL,
        ], check=True, timeout=120, capture_output=True)
    print(f"  {out}")


if __name__ == "__main__":
    w = int(sys.argv[1]) if len(sys.argv) > 1 else 1920
    h = int(sys.argv[2]) if len(sys.argv) > 2 else 1080
    target = Path(sys.argv[3]) if len(sys.argv) > 3 else HERE / "figures" / "app.png"
    shoot(target, w, h)
