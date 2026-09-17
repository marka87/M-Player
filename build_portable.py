"""Backward-compatibility trampoline for build_portable.py."""
import sys
from pathlib import Path
import subprocess

if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "scripts" / "build_portable.py"
    sys.exit(subprocess.run([sys.executable, str(target)] + sys.argv[1:]).returncode)

