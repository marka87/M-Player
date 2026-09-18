# 🛠️ M-Player — Terminal & Git Spickzettel (Cheat Sheet)

Eine praktische Übersicht aller wichtigen Terminal-Befehle für die Entwicklung, Versionierung und Veröffentlichung von M-Player.

---

## 1. 🔄 Tägliche Git-Befehle (Arbeiten & Synchronisieren)

| Befehl | Erklärung |
| :--- | :--- |
| `git status` | Zeigt geänderte, neue oder gelöschte Dateien an. |
| `git diff` | Zeigt die genauen Code-Änderungen an, bevor du committest. |
| `git pull` | Holt die neuesten Änderungen von GitHub auf deinen PC. |
| `git add .` | Merkt alle geänderten Dateien für den nächsten Commit vor. |
| `git commit -m "Deine Nachricht"` | Erstellt einen Commit mit deiner Beschreibung. |
| `git commit -am "Deine Nachricht"` | **Schnell-Befehl:** `add` und `commit` in einem Schritt (für getrackte Dateien). |
| `git push` | Lädt deine lokalen Commits auf GitHub hoch. |
| `git log --oneline -n 5` | Zeigt die letzten 5 Commits kompakt in einer Zeile an. |

---

## 2. 🏷️ Versionsverwaltung (`scripts/bump_version.py`)

Dein Projekt besitzt ein Skript, das die Version automatisch in `src/__init__.py` und `CHANGELOG.md` hochzählt:

```powershell
# Aktuelle Version anzeigen
py scripts/bump_version.py current

# Version automatisch erhöhen:
py scripts/bump_version.py patch    # Für Bugfixes & kleine Tweaks (z. B. v1.0.3 -> v1.0.4)
py scripts/bump_version.py minor    # Für neue Features & Ansichten (z. B. v1.0.3 -> v1.1.0)
py scripts/bump_version.py major    # Für große Umbauten / Major Releases (z. B. v1.0.3 -> v2.0.0)

# Oder direkt eine feste Version setzen:
py scripts/bump_version.py 1.2.0
```

---

## 3. 🚀 Tags & GitHub Actions Release (Automatischer Download-Build)

Ein Git-Tag triggert automatisch deine GitHub Actions Pipeline, die eine fertige Windows Portable `.zip` und Linux `.tar.gz / AppImage` baut und als GitHub Release veröffentlicht:

```powershell
# 1. Tag lokal erstellen (z. B. v1.0.4)
git tag v1.0.4

# 2. Tag zusammen mit deinem Code zu GitHub pushen (startet den Build-Prozess!)
git push origin main --tags

# Vorhandene Tags ansehen
git tag

# Tag löschen (falls du dich vertippt hast):
git tag -d v1.0.4                     # Lokal löschen
git push origin --delete v1.0.4       # Auf GitHub löschen
```

---

## 4. 📦 Lokales Bauen der Portable-Version (ZIP)

Wenn du die portable `.exe` und `.zip` direkt auf deinem Rechner ohne GitHub bauen willst:

```powershell
# Kompletter Build (kompiliert PyInstaller, packt Assets & Icons, schnürt die ZIP)
py build_portable.py

# Schneller Re-Pack (überspringt PyInstaller, packt nur Icons/Assets neu)
py build_portable.py --skip-compile
```

*Die fertigen Dateien findest du danach im Ordner `dist/`:*
- `dist/M-Player-Portable/` (Entpackter Ordner mit `M-Player.exe`)
- `dist/M-Player-Windows-vX.X.X.zip` (Die fertige ZIP-Datei zum Weitergeben)

---

## 5. 🧪 App starten & Tests prüfen

```powershell
# App direkt im Entwicklungsmodus ausführen
py main.py

# Sprachtests ausführen (prüft DE, EN, HU Vollständigkeit)
py test_i18n.py

# Duplikate-Finder Tests
py test_duplicates.py

# Smoke- & Basistests
py test_smoke.py
```

---

## 6. ⚠️ Notfall & Änderungen rückgängig machen

```powershell
# Alle noch nicht committeten Änderungen verwerfen (bringt Code auf letzten Commit zurück)
git restore .

# Nicht getrackte, neue temporäre Dateien aufräumen
git clean -fd

# Einen neuen Test-Branch erstellen & dorthin wechseln
git checkout -b feature/mein-neues-feature

# Wieder zurück zum Haupt-Branch (main) wechseln
git checkout main
```

---

## 💡 Der 1-Klick Release-Befehl (Alles automatisch!)

Anstatt 4 Befehle nacheinander einzugeben, kannst du **alles in einem einzigen Befehl** erledigen:

```powershell
# Erhöht Version (z. B. v1.0.3 -> v1.0.4), committet, taggt und pusht direkt zu GitHub:
py scripts/release.py patch

# Für neue Features (Minor Release, z. B. v1.1.0):
py scripts/release.py minor

# Für eine ganz bestimmte Version:
py scripts/release.py 1.0.5
```
*Das startet sofort online auf GitHub Actions den Build für Windows Portable ZIP & Linux AppImage!*

---

## 💡 Manuelle Schritte (falls du es Schritt für Schritt machen willst)

```powershell
# 1. Version erhöhen
py scripts/bump_version.py patch

# 2. Änderungen committen & pushen
git commit -am "release: v1.0.4"
git push

# 3. Tag setzen & hochladen (startet GitHub Build)
git tag v1.0.4
git push origin --tags
```
Danach kannst du auf deiner GitHub-Repository-Seite unter **Releases** bzw. **Actions** zuschauen, wie GitHub die fertigen `.zip`- und Linux-Dateien baut!

