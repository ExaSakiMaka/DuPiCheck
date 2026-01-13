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
                    size INTEGER
                )
                """
            )
            conn.commit()
            cur.execute("SELECT path, hash, mtime, size FROM images")
            for r in cur.fetchall():
                db_entries[r[0]] = (r[1], r[2], r[3])
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
                    if entry and entry[1] == mtime and entry[2] == size:
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
                    if entry and entry[1] == mtime and entry[2] == size:
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

def find_duplicates(hashes, threshold=HASH_DISTANCE_THRESHOLD):
    duplicates = []
    used = set()

    for (p1, h1), (p2, h2) in combinations(hashes.items(), 2):
        if p1 in used or p2 in used:
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

# ================= CLI =================

def print_duplicates(duplicates):
    if not duplicates:
        print("No duplicates found.")
        return
    for orig, dup, dist in duplicates:
        print(f"\nORIGINAL: {orig}\nDUPLICATE: {dup}\nDistance: {dist}")
    print(f"\nFound {len(duplicates)} duplicates.")


def scan_folder(folder, threshold, use_db=True, rebuild_cache=False, db_file=None):
    print(f"Scanning folder: {folder}")
    paths = get_image_paths(folder)
    # determine DB path (per-folder default)
    db_path = db_file if db_file else os.path.join(folder, ".dupicheck.db")
    if not use_db:
        db_path = None
    hashes = compute_hashes(paths, db_path=db_path, use_db=(use_db and db_path is not None), rebuild=rebuild_cache)
    duplicates = find_duplicates(hashes, threshold=threshold)
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


if __name__ == "__main__":
    main()
