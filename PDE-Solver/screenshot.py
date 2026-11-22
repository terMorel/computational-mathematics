"""Скриншот работающего приложения для README и титульного слайда.

Сначала запустите приложение (python app.py), затем: python screenshot.py
Нужен Google Chrome; путь можно передать первым аргументом.
"""

from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).parent
CHROME = sys.argv[1] if len(sys.argv) > 1 else "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def shoot(url, out, width=1920, height=1080):
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([
            CHROME, "--headless=new", f"--user-data-dir={profile}", "--hide-scrollbars",
            f"--window-size={width},{height}", "--force-device-scale-factor=1",
            "--enable-unsafe-swiftshader", "--use-angle=swiftshader", "--ignore-gpu-blocklist",
            "--virtual-time-budget=25000", "--run-all-compositor-stages-before-draw",
            f"--screenshot={out}", url,
        ], check=True, timeout=120, capture_output=True)
    print("  " + str(Path(out).relative_to(HERE)))


if __name__ == "__main__":
    shoot("http://127.0.0.1:8050/", HERE / "figures" / "app.png")
