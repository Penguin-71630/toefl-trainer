"""Start the backend (uvicorn) and the Textual frontend together.

Usage:  python run.py            # backend + frontend
        python run.py backend    # backend only (for development)
"""

import os
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))


def load_env() -> None:
    env_file = BASE / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    load_env()
    backend_only = len(sys.argv) > 1 and sys.argv[1] == "backend"

    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app",
         "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
        cwd=BASE)
    try:
        if backend_only:
            backend.wait()
        else:
            from frontend.toefl import ToeflApp
            ToeflApp().run()
    finally:
        backend.terminate()
        backend.wait()


if __name__ == "__main__":
    main()
