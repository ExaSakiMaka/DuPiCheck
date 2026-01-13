import os
import shutil
import sys
from itertools import combinations
import sqlite3

# dependencies: guard imports with helpful messages
try:
    from PIL import Image
except Exception:
    print("Missing dependency: Pillow. Install with: pip install Pillow")
    sys.exit(1)

try:
    import imagehash
except Exception:
    print("Missing dependency: ImageHash. Install with: pip install ImageHash")
    sys.exit(1)

try:
    from tqdm import tqdm
except Exception:
    # fallback: simple iterator if tqdm not available
    def tqdm(x, **kwargs):
        return x

import argparse

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")
HASH_DISTANCE_THRESHOLD = 5  # lower = stricter

def get_image_paths(folder):
    paths = []
    for root, _, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(IMAGE_EXTENSIONS):
                paths.append(os.path.join(root, f))
    return paths

def compute_hashes(image_paths, db_path=None, use_db=True, rebuild=False, progress_callback=None):
    """Compute perceptual hashes for image paths.

    If `db_path` is provided and `use_db` is True, use an SQLite DB to cache hashes keyed by
    file path, mtime and size to avoid recomputing unchanged images. If `rebuild` is True,
    recompute all hashes and update the DB.

    Progress behavior:
      - If `progress_callback` is provided it will be called as progress_callback(index, total, path).
      - Otherwise a tqdm progress bar is shown by default (if available).
    """
    hashes = {}

    conn = None
    cur = None
    db_entries = {}

    if use_db and db_path:
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS images (
                    path TEXT PRIMARY KEY,
                    hash TEXT,
                    mtime REAL,
                    size INTEGER,
                    ignored INTEGER DEFAULT 0
                )
                """
            )
            # ensure ignored column exists for older DBs
            cur.execute("PRAGMA table_info(images)")
            cols = [r[1] for r in cur.fetchall()]
            if 'ignored' not in cols:
                try:
                    cur.execute("ALTER TABLE images ADD COLUMN ignored INTEGER DEFAULT 0")
                except Exception:
                    pass
            conn.commit()
            cur.execute("SELECT path, hash, mtime, size, COALESCE(ignored,0) FROM images")
            for r in cur.fetchall():
                # store hash, mtime, size, ignored
                db_entries[r[0]] = (r[1], r[2], r[3], r[4])
        except Exception as e:
            print(f"Warning: could not open DB {db_path}: {e}")
            if conn:
                conn.close()
            conn = None
            cur = None

    total = len(image_paths)

    # If a callback is provided, use it; otherwise show tqdm progress by default
    if progress_callback:
        for i, path in enumerate(image_paths):
            try:
                progress_callback(i + 1, total, path)
            except Exception:
                pass

            try:
                st = os.stat(path)
                mtime = st.st_mtime
                size = st.st_size
                used_cached = False

                if cur and not rebuild:
                    entry = db_entries.get(path)
                    # only use cached entry if not marked ignored (entry[3] == 1 means ignored)
                    if entry and entry[1] == mtime and entry[2] == size and (len(entry) < 4 or entry[3] == 0):
                        try:
                            hashes[path] = imagehash.hex_to_hash(entry[0])
                            used_cached = True
                        except Exception:
                            used_cached = False

                if not used_cached:
                    with Image.open(path) as img:
                        h = imagehash.phash(img)
                        hashes[path] = h
                        if cur:
                            cur.execute(
                                "REPLACE INTO images (path, hash, mtime, size) VALUES (?,?,?,?)",
                                (path, str(h), mtime, size),
                            )
            except Exception:
                pass
    else:
        # use tqdm by default for a visual progress bar
        tq = tqdm(total=total, desc="Hashing images", unit='img')
        for i, path in enumerate(image_paths):
            try:
                tq.set_description(f"Hashing: {os.path.basename(path)}")
                st = os.stat(path)
                mtime = st.st_mtime
                size = st.st_size
                used_cached = False

                if cur and not rebuild:
                    entry = db_entries.get(path)
                    # only use cached entry if not marked ignored (entry[3] == 1 means ignored)
                    if entry and entry[1] == mtime and entry[2] == size and (len(entry) < 4 or entry[3] == 0):
                        try:
                            hashes[path] = imagehash.hex_to_hash(entry[0])
                            used_cached = True
                        except Exception:
                            used_cached = False

                if not used_cached:
                    with Image.open(path) as img:
                        h = imagehash.phash(img)
                        hashes[path] = h
                        if cur:
                            cur.execute(
                                "REPLACE INTO images (path, hash, mtime, size) VALUES (?,?,?,?)",
                                (path, str(h), mtime, size),
                            )
            except Exception:
                pass
            tq.update(1)
        tq.close()

    # remove DB entries for files that no longer exist
    if cur:
        try:
            existing = set(image_paths)
            cur.execute("SELECT path FROM images")
            for (p,) in cur.fetchall():
                if p not in existing:
                    cur.execute("DELETE FROM images WHERE path=?", (p,))
            conn.commit()
        except Exception:
            pass
        finally:
            conn.close()

    return hashes

def find_duplicates(hashes, threshold=HASH_DISTANCE_THRESHOLD, ignored_pairs=None):
    """Find duplicate pairs from hashes, skipping any pair present in `ignored_pairs` set.

    `ignored_pairs` should be a set of frozenset({path1, path2})."""
    duplicates = []
    used = set()
    ignored_pairs = ignored_pairs or set()

    for (p1, h1), (p2, h2) in combinations(hashes.items(), 2):
        if p1 in used or p2 in used:
            continue
        # skip if this exact pair is marked ignored
        if frozenset((p1, p2)) in ignored_pairs:
            continue
        if h1 - h2 <= threshold:
            duplicates.append((p1, p2, h1 - h2))
            used.add(p2)

    return duplicates

def move_duplicates(duplicates, target_folder):
    os.makedirs(target_folder, exist_ok=True)
    for _, dup, _ in duplicates:
        shutil.move(dup, os.path.join(target_folder, os.path.basename(dup)))


def _unique_dest_path(dest_folder, name):
    base = name
    dest = os.path.join(dest_folder, base)
    i = 1
    while os.path.exists(dest):
        name_no_ext, ext = os.path.splitext(base)
        dest = os.path.join(dest_folder, f"{name_no_ext}_{i}{ext}")
        i += 1
    return dest


def delete_with_checks(duplicates, manual_dir, manual_threshold=2):
    """
    For each duplicate pair:
      - If distance > manual_threshold: move both files into their own subfolder under `manual_dir` for manual inspection.
      - Else: keep the largest file and delete the other.

    Each moved pair is placed in a folder named `pair_###` containing both files and an `info.txt` describing the pair.
    """
    os.makedirs(manual_dir, exist_ok=True)
    moved_for_manual = []   # flat list of files moved
    pair_dirs = []          # list of pair subfolders created
    deleted = []
    kept = []
    pair_idx = 1

    for p1, p2, dist in duplicates:
        try:
            if dist > manual_threshold:
                # create a subfolder for this pair
                pair_name = f"pair_{pair_idx:03d}"
                pair_dir = os.path.join(manual_dir, pair_name)
                os.makedirs(pair_dir, exist_ok=True)

                dest1 = _unique_dest_path(pair_dir, os.path.basename(p1))
                dest2 = _unique_dest_path(pair_dir, os.path.basename(p2))
                shutil.move(p1, dest1)
                shutil.move(p2, dest2)
                moved_for_manual.extend([dest1, dest2])
                pair_dirs.append(pair_dir)

                # write a small info file for manual inspection
                try:
                    with open(os.path.join(pair_dir, "info.txt"), "w") as f:
                        f.write(f"Original1: {p1}\nOriginal2: {p2}\nDistance: {dist}\n")
                except Exception:
                    pass

                pair_idx += 1
            else:
                size1 = os.path.getsize(p1) if os.path.exists(p1) else -1
                size2 = os.path.getsize(p2) if os.path.exists(p2) else -1
                # keep the biggest file; delete the other
                if size1 >= size2:
                    to_delete = p2
                    kept.append(p1)
                else:
                    to_delete = p1
                    kept.append(p2)
                if os.path.exists(to_delete):
                    os.remove(to_delete)
                    deleted.append(to_delete)
        except Exception as e:
            print(f"Error processing pair ({p1}, {p2}): {e}")

    # summary
    if pair_dirs:
        print(f"Moved {len(pair_dirs)} pairs ({len(moved_for_manual)} files) to manual check folder: {manual_dir}")
    else:
        print("No files moved for manual check.")

    if deleted:
        print(f"Deleted {len(deleted)} files.")
    else:
        print("No files deleted.")

    if kept:
        print(f"Kept {len(kept)} files.")
    else:
        print("No files kept.")

    return {"moved": moved_for_manual, "moved_pairs": pair_dirs, "deleted": deleted, "kept": kept}


def db_status(db_path):
    """Return basic statistics about the cache DB: number of entries and mtime ranges."""
    if not db_path or not os.path.exists(db_path):
        print(f"DB file not found: {db_path}")
        return None

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), MIN(mtime), MAX(mtime) FROM images")
        cnt, min_mtime, max_mtime = cur.fetchone()
        conn.close()
    except Exception as e:
        print(f"Error reading DB {db_path}: {e}")
        return None

    try:
        db_stat_mtime = os.path.getmtime(db_path)
        db_size = os.path.getsize(db_path)
    except Exception:
        db_stat_mtime = None
        db_size = None

    print(f"DB: {db_path}")
    print(f"  Entries: {cnt}")
    if min_mtime and max_mtime:
        print(f"  Images mtime range: {min_mtime} - {max_mtime}")
    if db_stat_mtime:
        print(f"  DB file mtime: {db_stat_mtime}")
    if db_size is not None:
        print(f"  DB file size: {db_size} bytes")

    return {"entries": cnt, "min_mtime": min_mtime, "max_mtime": max_mtime, "db_mtime": db_stat_mtime, "db_size": db_size}


def set_ignored(paths, db_path):
    """Mark given file paths as ignored in the DB (create/update entries)."""
    if not db_path:
        return
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS images (
                path TEXT PRIMARY KEY,
                hash TEXT,
                mtime REAL,
                size INTEGER,
                ignored INTEGER DEFAULT 0
            )
            """
        )
        # ensure ignored column
        cur.execute("PRAGMA table_info(images)")
        cols = [r[1] for r in cur.fetchall()]
        if 'ignored' not in cols:
            try:
                cur.execute("ALTER TABLE images ADD COLUMN ignored INTEGER DEFAULT 0")
            except Exception:
                pass

        for p in paths:
            try:
                if os.path.exists(p):
                    st = os.stat(p)
                    with Image.open(p) as img:
                        h = str(imagehash.phash(img))
                    cur.execute(
                        "REPLACE INTO images (path, hash, mtime, size, ignored) VALUES (?,?,?,?,1)",
                        (p, h, st.st_mtime, st.st_size),
                    )
                else:
                    # if file doesn't exist, just mark ignored by path (hash NULL)
                    cur.execute(
                        "REPLACE INTO images (path, hash, mtime, size, ignored) VALUES (?,?,?,?,1)",
                        (p, None, 0, 0),
                    )
            except Exception as e:
                print(f"Warning: could not mark {p} ignored: {e}")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error updating DB {db_path}: {e}")


def reintegrate_manual(manual_dir, db_file=None, dry_run=False, remove_empty=True, mark_ignored_if_both=True):
    """Restore files from manual pair folders back to original locations.

    Expects pair folders (pair_###) inside `manual_dir` and an `info.txt` in each that contains
    lines `Original1: <path>` and `Original2: <path>` (written by `delete_with_checks`).

    If both files are restored and `mark_ignored_if_both` is True, this will set `ignored` in the DB
    for both restored file paths so future scans will ignore them as duplicates.
    """
    if not os.path.isdir(manual_dir):
        print(f"Manual directory not found: {manual_dir}")
        return

    moved_back = []
    pairs_restored = []

    for entry in sorted(os.listdir(manual_dir)):
        pair_path = os.path.join(manual_dir, entry)
        if not os.path.isdir(pair_path):
            continue
        info_file = os.path.join(pair_path, "info.txt")
        origs = []
        if os.path.exists(info_file):
            try:
                with open(info_file, "r") as f:
                    for line in f:
                        if line.startswith("Original1:") or line.startswith("Original2:"):
                            origs.append(line.split(":", 1)[1].strip())
            except Exception:
                pass

        # map basename -> original path (best effort)
        basename_map = {os.path.basename(p): p for p in origs}

        files_in_pair = [f for f in os.listdir(pair_path) if f != 'info.txt']
        restored = []
        for fname in files_in_pair:
            src = os.path.join(pair_path, fname)
            dest = None
            # if we have original path, use it; otherwise restore to parent of manual_dir
            if fname in basename_map:
                intended = basename_map[fname]
                dest_dir = os.path.dirname(intended)
                os.makedirs(dest_dir, exist_ok=True)
                dest = _unique_dest_path(dest_dir, fname)
            else:
                # fallback: restore to manual_dir parent
                parent = os.path.dirname(manual_dir)
                dest = _unique_dest_path(parent, fname)

            if dry_run:
                print(f"Would move {src} -> {dest}")
            else:
                try:
                    shutil.move(src, dest)
                    moved_back.append(dest)
                    restored.append(dest)
                except Exception as e:
                    print(f"Failed to move {src} -> {dest}: {e}")

        if restored:
            pairs_restored.append((pair_path, restored))

        # remove pair folder if empty
        if remove_empty and not dry_run:
            try:
                if not os.listdir(pair_path):
                    os.rmdir(pair_path)
            except Exception:
                pass

    # if required, mark ignored in DB when both files in a pair were restored
    if mark_ignored_if_both and pairs_restored and db_file:
        for pair_path, restored in pairs_restored:
            if len(restored) >= 2:
                # mark the restored paths as ignored
                set_ignored(restored, db_file)
                # also record the pair so the two files are not compared to each other
                try:
                    conn = sqlite3.connect(db_file)
                    cur = conn.cursor()
                    cur.execute(
                        """
                        CREATE TABLE IF NOT EXISTS ignored_pairs (
                            p1 TEXT,
                            p2 TEXT
                        )
                        """
                    )
                    p1, p2 = restored[0], restored[1]
                    cur.execute("REPLACE INTO ignored_pairs (p1, p2) VALUES (?,?)", (p1, p2))
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

    print(f"Restored {len(moved_back)} files from manual dir {manual_dir}")
    return {"restored": moved_back, "pairs": pairs_restored}

# ================= CLI =================

def print_duplicates(duplicates):
    if not duplicates:
        print("No duplicates found.")
        return
    for orig, dup, dist in duplicates:
        print(f"\nORIGINAL: {orig}\nDUPLICATE: {dup}\nDistance: {dist}")
    print(f"\nFound {len(duplicates)} duplicates.")


def load_ignored_pairs(db_path):
    pairs = set()
    if not db_path or not os.path.exists(db_path):
        return pairs
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ignored_pairs (
                p1 TEXT,
                p2 TEXT
            )
            """
        )
        cur.execute("SELECT p1, p2 FROM ignored_pairs")
        for a, b in cur.fetchall():
            pairs.add(frozenset((a, b)))
        conn.close()
    except Exception:
        pass
    return pairs


def list_ignored_pairs(db_path):
    """Return an ordered list of (p1, p2) tuples from `ignored_pairs` table."""
    pairs = []
    if not db_path or not os.path.exists(db_path):
        return pairs
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS ignored_pairs (
                p1 TEXT,
                p2 TEXT
            )
            """
        )
        cur.execute("SELECT p1, p2 FROM ignored_pairs")
        for a, b in cur.fetchall():
            pairs.append((a, b))
        conn.close()
    except Exception:
        pass
    return pairs


def print_ignored_pairs(db_path):
    pairs = list_ignored_pairs(db_path)
    if not pairs:
        print("No ignored pairs recorded.")
        return pairs
    for i, (a, b) in enumerate(pairs, start=1):
        print(f"{i}: {a}  <->  {b}")
    print(f"\nTotal ignored pairs: {len(pairs)}")
    return pairs


def remove_ignored_pair(db_path, p1, p2):
    """Remove a pair entry matching p1/p2 (order-insensitive). Returns True if removed."""
    if not db_path or not os.path.exists(db_path):
        return False
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM ignored_pairs WHERE (p1=? AND p2=?) OR (p1=? AND p2=?)",
            (p1, p2, p2, p1),
        )
        conn.commit()
        affected = cur.rowcount
        conn.close()
        return affected > 0
    except Exception:
        return False


def scan_folder(folder, threshold, use_db=True, rebuild_cache=False, db_file=None):
    print(f"Scanning folder: {folder}")
    paths = get_image_paths(folder)
    # determine DB path (per-folder default)
    db_path = db_file if db_file else os.path.join(folder, ".dupicheck.db")
    if not use_db:
        db_path = None
    hashes = compute_hashes(paths, db_path=db_path, use_db=(use_db and db_path is not None), rebuild=rebuild_cache)
    ignored = load_ignored_pairs(db_path) if db_path else set()
    duplicates = find_duplicates(hashes, threshold=threshold, ignored_pairs=ignored)
    print_duplicates(duplicates)
    return duplicates


def main():
    parser = argparse.ArgumentParser(description="Duplicate Image Finder (CLI)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_scan = subparsers.add_parser("scan", help="Scan folder for duplicate images")
    p_scan.add_argument("folder", help="Folder to scan")
    p_scan.add_argument("-t", "--threshold", type=int, default=HASH_DISTANCE_THRESHOLD, help="Hash distance threshold")
    p_scan.add_argument("--no-cache", "-n", action="store_true", help="Disable cache, recompute all hashes")
    p_scan.add_argument("--rebuild-cache", "-r", action="store_true", help="Force recompute and update cache")
    p_scan.add_argument("--db-file", help="Path to DB file to use for caching (default: <folder>/.dupicheck.db)")

    p_move = subparsers.add_parser("move", help="Move duplicates to target folder")
    p_move.add_argument("folder", help="Folder to scan")
    p_move.add_argument("target", help="Destination folder")
    p_move.add_argument("-t", "--threshold", type=int, default=HASH_DISTANCE_THRESHOLD, help="Hash distance threshold")
    p_move.add_argument("--no-cache", "-n", action="store_true", help="Disable cache, recompute all hashes")
    p_move.add_argument("--rebuild-cache", "-r", action="store_true", help="Force recompute and update cache")
    p_move.add_argument("--db-file", help="Path to DB file to use for caching (default: <folder>/.dupicheck.db)")

    p_delete = subparsers.add_parser("delete", help="Delete duplicate images")
    p_delete.add_argument("folder", help="Folder to scan")
    p_delete.add_argument("-y", "--yes", action="store_true", help="Confirm deletion without prompt")
    p_delete.add_argument("-t", "--threshold", type=int, default=HASH_DISTANCE_THRESHOLD, help="Hash distance threshold")
    p_delete.add_argument("-m", "--manual-dir", help="Directory to move uncertain pairs for manual check (default: <folder>_manual_check)")
    p_delete.add_argument("-M", "--manual-threshold", type=int, default=2, help="Distance above which pairs are moved for manual check (default: 2)")
    p_delete.add_argument("--no-cache", "-n", action="store_true", help="Disable cache, recompute all hashes")
    p_delete.add_argument("--rebuild-cache", "-r", action="store_true", help="Force recompute and update cache")
    p_delete.add_argument("--db-file", help="Path to DB file to use for caching (default: <folder>/.dupicheck.db)")

    p_status = subparsers.add_parser("status", help="Show cache DB status for a folder")
    p_status.add_argument("folder", help="Folder to inspect (used to find .dupicheck.db)")
    p_status.add_argument("--db-file", help="Path to DB file to use for status (default: <folder>/.dupicheck.db)")

    p_ignored = subparsers.add_parser("ignored", help="List/manage ignored pairs")
    ignored_sub = p_ignored.add_subparsers(dest="ignored_command", required=True)

    p_ignored_list = ignored_sub.add_parser("list", help="List ignored pairs")
    p_ignored_list.add_argument("folder", help="Folder to inspect (used to find .dupicheck.db)")
    p_ignored_list.add_argument("--db-file", help="Path to DB file to use (default: <folder>/.dupicheck.db)")

    p_ignored_remove = ignored_sub.add_parser("remove", help="Remove an ignored pair by index or by providing both paths")
    p_ignored_remove.add_argument("folder", help="Folder to inspect (used to find .dupicheck.db)")
    group = p_ignored_remove.add_mutually_exclusive_group(required=True)
    group.add_argument("-i", "--index", type=int, help="Index (shown by `ignored list`) of the pair to remove (1-based)")
    group.add_argument("-p", "--paths", nargs=2, help="Two file paths comprising the pair to remove (order-insensitive)")
    p_ignored_remove.add_argument("--db-file", help="Path to DB file to use (default: <folder>/.dupicheck.db)")

    args = parser.parse_args()

    if args.command == "scan":
        scan_folder(args.folder, args.threshold, use_db=not args.no_cache, rebuild_cache=args.rebuild_cache, db_file=args.db_file)
    elif args.command == "move":
        duplicates = scan_folder(args.folder, args.threshold, use_db=not args.no_cache, rebuild_cache=args.rebuild_cache, db_file=args.db_file)
        if not duplicates:
            sys.exit(0)
        move_duplicates(duplicates, args.target)
        print("Duplicates moved successfully.")
    elif args.command == "delete":
        duplicates = scan_folder(args.folder, args.threshold, use_db=not args.no_cache, rebuild_cache=args.rebuild_cache, db_file=args.db_file)
        if not duplicates:
            sys.exit(0)
        if not args.yes:
            resp = input("Are you sure you want to DELETE duplicates? [y/N]: ").strip().lower()
            if resp != "y":
                print("Aborted.")
                sys.exit(0)
        manual_dir = args.manual_dir if getattr(args, 'manual_dir', None) else os.path.join(args.folder, "manual_check")
        res = delete_with_checks(duplicates, manual_dir, manual_threshold=args.manual_threshold)
        print("Done.")
    elif args.command == "status":
        db_path = args.db_file if getattr(args, 'db_file', None) else os.path.join(args.folder, ".dupicheck.db")
        db_status(db_path)
    elif args.command == "ignored":
        db_path = args.db_file if getattr(args, 'db_file', None) else os.path.join(args.folder, ".dupicheck.db")
        if args.ignored_command == "list":
            print_ignored_pairs(db_path)
        elif args.ignored_command == "remove":
            if getattr(args, 'index', None):
                idx = args.index
                pairs = list_ignored_pairs(db_path)
                if idx < 1 or idx > len(pairs):
                    print(f"Index {idx} out of range")
                    sys.exit(1)
                p1, p2 = pairs[idx - 1]
                ok = remove_ignored_pair(db_path, p1, p2)
                if ok:
                    print(f"Removed ignored pair {idx}: {p1} <-> {p2}")
                else:
                    print("Failed to remove pair (maybe already removed).")
            elif getattr(args, 'paths', None):
                p1, p2 = args.paths
                ok = remove_ignored_pair(db_path, p1, p2)
                if ok:
                    print(f"Removed ignored pair: {p1} <-> {p2}")
                else:
                    print("Pair not found or failed to remove.")


if __name__ == "__main__":
    main()
