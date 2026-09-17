#!/usr/bin/env python3
"""Automated Semantic Version Bumper for M-Player.

Usage:
    python scripts/bump_version.py patch       # e.g. v1.0.2 -> v1.0.3 (Bugfixes, kleine Tweaks)
    python scripts/bump_version.py minor       # e.g. v1.0.2 -> v1.1.0 (Neue Features)
    python scripts/bump_version.py major       # e.g. v1.0.2 -> v2.0.0 (Große Refactorings/Breaking Changes)
    python scripts/bump_version.py current     # Gibt nur die aktuelle Version aus
    python scripts/bump_version.py 1.2.0       # Setzt direkt eine feste Version
"""

import re
import sys
from datetime import date
from pathlib import Path
import subprocess

ROOT_DIR = Path(__file__).resolve().parents[1]
INIT_PY = ROOT_DIR / "src" / "__init__.py"
CHANGELOG_MD = ROOT_DIR / "CHANGELOG.md"


def get_current_version() -> str:
    """Extract current version string from src/__init__.py."""
    if not INIT_PY.exists():
        raise FileNotFoundError(f"Could not find {INIT_PY}")
    content = INIT_PY.read_text(encoding="utf-8")
    m = re.search(r'__version__\s*=\s*["\']v?([^"\']+)["\']', content)
    if not m:
        raise ValueError(f"No __version__ found in {INIT_PY}")
    return m.group(1).strip()


def compute_next_version(current: str, bump_type: str) -> str:
    """Compute next semver version string."""
    parts = current.split(".")
    while len(parts) < 3:
        parts.append("0")

    try:
        major, minor, patch = map(int, parts[:3])
    except ValueError:
        raise ValueError(f"Ungültiges Versionsformat: '{current}'. Erwartet wird X.Y.Z")

    bump = bump_type.lower().strip()
    if bump == "patch":
        patch += 1
    elif bump == "minor":
        minor += 1
        patch = 0
    elif bump == "major":
        major += 1
        minor = 0
        patch = 0
    elif re.match(r"^v?\d+\.\d+(\.\d+)?$", bump):
        # Manuelle Versionsnummer angegeben
        return bump.lstrip("v")
    else:
        raise ValueError(f"Unbekannter Bump-Typ: '{bump_type}'. Erlaubt sind: patch, minor, major oder z.B. 1.0.3")

    return f"{major}.{minor}.{patch}"


def update_init_py(new_ver: str) -> None:
    """Update __version__ in src/__init__.py."""
    content = INIT_PY.read_text(encoding="utf-8")
    new_content = re.sub(
        r'__version__\s*=\s*["\'][^"\']+["\']',
        f'__version__ = "v{new_ver}"',
        content,
    )
    INIT_PY.write_text(new_content, encoding="utf-8")
    print(f"  [x] src/__init__.py -> v{new_ver}")


def update_changelog(new_ver: str) -> None:
    """Prepend new version section to CHANGELOG.md if not present."""
    if not CHANGELOG_MD.exists():
        return

    content = CHANGELOG_MD.read_text(encoding="utf-8")
    header_pattern = rf"##\s*\[{re.escape(new_ver)}\]"
    if re.search(header_pattern, content):
        print(f"  [-] CHANGELOG.md enthält bereits einen Eintrag für [{new_ver}]")
        return

    today = date.today().isoformat()
    template = f"""## [{new_ver}] - {today}

### Added
- 

### Changed
- 

### Fixed
- 

"""
    # Insert after the first header / description
    first_version_match = re.search(r"\n##\s*\[", content)
    if first_version_match:
        pos = first_version_match.start() + 1
        new_content = content[:pos] + template + content[pos:]
    else:
        new_content = content + "\n" + template

    CHANGELOG_MD.write_text(new_content, encoding="utf-8")
    print(f"  [x] CHANGELOG.md -> Neuer Abschnitt für [{new_ver}] - {today} hinzugefügt")


def main():
    if len(sys.argv) < 2:
        curr = get_current_version()
        print(f"Aktuelle Version: v{curr}")
        print("\nVerwendung:")
        print("  python scripts/bump_version.py patch   (z. B. v1.0.2 -> v1.0.3)")
        print("  python scripts/bump_version.py minor   (z. B. v1.0.2 -> v1.1.0)")
        print("  python scripts/bump_version.py major   (z. B. v1.0.2 -> v2.0.0)")
        print("  python scripts/bump_version.py current")
        return

    action = sys.argv[1].strip()
    curr = get_current_version()

    if action == "current":
        print(f"v{curr}")
        return

    next_ver = compute_next_version(curr, action)
    print(f"\n🚀 Version wird erhöht: v{curr} -> v{next_ver}")

    update_init_py(next_ver)
    update_changelog(next_ver)

    print(f"\n✅ Erfolgreich auf v{next_ver} aktualisiert!")
    print("\nNächste Schritte:")
    print("  1. Bearbeite kurz CHANGELOG.md (Added / Changed / Fixed)")
    print(f"  2. git commit -am \"release: v{next_ver}\"")
    print(f"  3. git tag v{next_ver}")
    print(f"  4. git push origin main --tags")


if __name__ == "__main__":
    main()
