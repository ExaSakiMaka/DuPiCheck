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
- Move duplicates to a folder:
  ```bash
  ./DuPiCheck.sh move /path/to/images /path/to/dest -t 4
  ```
- Delete duplicates (keep largest file in pair; pairs with distance > manual-threshold are moved for manual review):
  ```bash
  ./DuPiCheck.sh delete /path/to/images -M 3 -m /tmp/manual_check -y
  ```

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
**/!\ GUI IS SHITTY AND MADE FOR FUN, EXPECT BUGS

Notes
- The `delete` command keeps the largest file in a pair and deletes the other. Pairs with distance greater than the manual-threshold (`-M`) are moved to the manual-check folder for review.
- The installer script assumes a Unix-like environment (Linux / macOS). On Windows, use the equivalent virtualenv activation commands.

License
- MIT-style (modify as desired).
