# DupPicCheck

Duplicate image finder and manager.

Features
- Find visually similar images using perceptual hashing (`imagehash`).
- CLI with commands: `scan`, `move`, `delete` (see examples below).
- Optional GUI frontend in `gui.py` that calls core functions.

Requirements
- Python 3.8+
- See `requirements.txt` for Python packages.

Quick install
1. Create a virtual environment and install dependencies (recommended):

   ```bash
   ./install.sh
   ```

2. Use the launcher to run the program (it activates `venv` automatically):

   ```bash
   ./DuPiCheck.sh --help
   ```

Launcher notes
- The launcher (`DuPiCheck.sh`) will try to activate `venv` at `./venv`.
- If `venv` is missing, the launcher will prompt to run `install.sh` (defaults to Yes). Use:
  - `--install` to automatically run the installer (non-interactive)
  - `--no-install` to skip installation and use the system Python

Usage examples
- Scan a folder (threshold short flag `-t`):
  ```bash
  ./DuPiCheck.sh scan /path/to/images -t 4
  ```

Progress is enabled by default
- CLI: a progress bar with the current filename is shown by default while hashing images.
- GUI: a progress bar and current filename are shown while scanning (UI remains responsive during scan).
- Move duplicates to a folder:
  ```bash
  ./DuPiCheck.sh move /path/to/images /path/to/dest -t 4
  ```
- Delete duplicates (keep largest file in pair; pairs with distance > manual-threshold are moved for manual review):
  ```bash
  ./DuPiCheck.sh delete /path/to/images -M 3 -m /tmp/manual_check -y
  ```
  When files are moved for manual review they are organized into numbered subfolders under the manual-check folder (e.g. `pair_001/`, `pair_002/`), each containing the two files and an `info.txt` describing the pair.
- Show cache DB status for a folder:
  ```bash
  ./DuPiCheck.sh status /path/to/images
  ```

Status notes
- Default DB path: `<folder>/.dupicheck.db` (can be overridden with `--db-file`).
- Output includes number of cached entries and DB file info.

Reintegrate manual checks
- After manually reviewing pairs moved to a manual folder, use `reintegrate_manual.py` to move the files back to their (original) locations and optionally mark them ignored in the DB so future runs won't consider those two files a duplicate pair.

Example:
```bash
# restore and mark ignored when both files in a pair are restored
./reintegrate_manual.py test/manual_check --db-file test/.dupicheck.db
```
Options:
- `--dry-run` : show actions without moving files
- `--no-remove` : do not remove empty pair folders after restoring
- `--no-mark` : do not mark restored pairs as ignored in DB

Manage ignored pairs
- You can list and remove ignored pairs recorded in the DB with the `ignored` command:
  - List (shows numbered pairs): `./DuPiCheck.sh ignored list /path/to/images` (or `python main.py ignored list /path`)
  - Remove by index (use the index shown by `ignored list`): `./DuPiCheck.sh ignored remove /path -i 1`
  - Remove by paths: `./DuPiCheck.sh ignored remove /path -p /path/to/a.jpg /path/to/b.jpg`
Notes:
- The ignored commands use the per-folder DB at `<folder>/.dupicheck.db` by default; pass `--db-file` to override.

Short flags
- `-t` / `--threshold` : hash distance threshold (scan/move/delete)
- `-y` / `--yes`       : skip confirmation for `delete`
- `-m` / `--manual-dir`: manual check destination for `delete`
- `-M` / `--manual-threshold`: threshold above which pairs are moved for manual review

Examples with launcher-only flags
- Force install and run a scan:
  ```bash
  ./DuPiCheck.sh --install scan /path -t 4
  ```
- Skip install and run with system Python:
  ```bash
  ./DuPiCheck.sh --no-install scan /path -t 4
  ```

GUI
- Launch the GUI (in the venv):
  ```bash
  source venv/bin/activate
  python gui.py
  ```
- The GUI provides a simple frontend and supports setting the manual-threshold (`M`) before performing delete operations (files with distance > M are moved to the selected manual-check folder).

Project status / verification
- Quick checks performed:
  - Syntax: Python files compile (no syntax errors)
  - Scripts: `DuPiCheck.sh` and `install.sh` are executable
  - Imports: `main` and `gui` import correctly when running inside the created `venv`
- Suggested next steps:
  - Add unit tests for `compute_hashes`, `find_duplicates`, and `delete_with_checks` (tests use `pytest`)
  - Add CI to run linting and tests on each push

Run tests locally:

```bash
pip install -r requirements.txt
pytest
```

Notes
- The `delete` command keeps the largest file in a pair and deletes the other. Pairs with distance greater than the manual-threshold (`-M`) are moved to the manual-check folder for review.
- The installer script assumes a Unix-like environment (Linux / macOS). On Windows, use the equivalent virtualenv activation commands.

License
- MIT-style (modify as desired).
