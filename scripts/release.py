#!/usr/bin/env python3
"""One-click release automation script for M-Player.

Usage:
    py scripts/release.py patch       # e.g. v1.0.3 -> v1.0.4
    py scripts/release.py minor       # e.g. v1.0.3 -> v1.1.0
    py scripts/release.py 1.0.5       # specific version
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.bump_version import get_current_version, compute_next_version, update_init_py, update_changelog


def run_cmd(cmd: list[str]) -> bool:
    print(f"\n> {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=ROOT_DIR)
    if res.returncode != 0:
        print(f"❌ Fehler bei: {' '.join(cmd)}")
        return False
    return True


def main():
    if len(sys.argv) < 2:
        curr = get_current_version()
        print(f"Aktuelle Version: v{curr}")
        print("\nVerwendung mit einem Befehl:")
        print("  py scripts/release.py patch    # Erhöht z. B. v1.0.3 -> v1.0.4, committet, taggt & pusht")
        print("  py scripts/release.py minor    # Erhöht z. B. v1.0.3 -> v1.1.0, committet, taggt & pusht")
        print("  py scripts/release.py 1.0.5    # Setzt direkt v1.0.5")
        return

    action = sys.argv[1].strip()
    curr = get_current_version()
    next_ver = compute_next_version(curr, action)
    tag_name = f"v{next_ver}"

    print("====================================================")
    print(f"  M-Player One-Click Release: v{curr} -> {tag_name}")
    print("====================================================")

    # 1. Update version in files
    print("\n[1/4] Aktualisiere Versionsdateien ...")
    update_init_py(next_ver)
    update_changelog(next_ver)

    # 2. Git commit
    print("\n[2/4] Erstelle Git Commit ...")
    if not run_cmd(["git", "add", "."]):
        sys.exit(1)
    if not run_cmd(["git", "commit", "-m", f"release: {tag_name}"]):
        sys.exit(1)

    # 3. Git tag
    print(f"\n[3/4] Erstelle Tag {tag_name} ...")
    if not run_cmd(["git", "tag", tag_name]):
        sys.exit(1)

    # 4. Git push with tags
    print("\n[4/4] Pushe Code & Tags zu GitHub (startet Online-Build) ...")
    if not run_cmd(["git", "push", "origin", "main", "--tags"]):
        sys.exit(1)

    print("\n====================================================")
    print(f"🎉 Erfolgreich! {tag_name} wurde auf GitHub gepusht.")
    print("GitHub Actions baut jetzt automatisch online die fertigen Pakete:")
    print("  - Windows Portable (.zip)")
    print("  - Linux AppImage & Tarball")
    print("Verfolge den Build live unter: https://github.com/marka87/M-Player/actions")
    print("====================================================")


if __name__ == "__main__":
    main()

