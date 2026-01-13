import os
import shutil
import sys
from itertools import combinations

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

def compute_hashes(image_paths):
    hashes = {}
    for path in tqdm(image_paths, desc="Hashing images"):
        try:
            with Image.open(path) as img:
                hashes[path] = imagehash.phash(img)
        except:
            pass
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
      - If distance > manual_threshold: move both files to manual_dir for manual inspection.
      - Else: keep the largest file and delete the other.
    """
    os.makedirs(manual_dir, exist_ok=True)
    moved_for_manual = []
    deleted = []
    kept = []

    for p1, p2, dist in duplicates:
        try:
            if dist > manual_threshold:
                # move both for manual inspection
                dest1 = _unique_dest_path(manual_dir, os.path.basename(p1))
                dest2 = _unique_dest_path(manual_dir, os.path.basename(p2))
                shutil.move(p1, dest1)
                shutil.move(p2, dest2)
                moved_for_manual.extend([dest1, dest2])
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
    if moved_for_manual:
        print(f"Moved {len(moved_for_manual)} files to manual check folder: {manual_dir}")
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

    return {"moved": moved_for_manual, "deleted": deleted, "kept": kept}

# ================= CLI =================

def print_duplicates(duplicates):
    if not duplicates:
        print("No duplicates found.")
        return
    for orig, dup, dist in duplicates:
        print(f"\nORIGINAL: {orig}\nDUPLICATE: {dup}\nDistance: {dist}")
    print(f"\nFound {len(duplicates)} duplicates.")


def scan_folder(folder, threshold):
    print(f"Scanning folder: {folder}")
    paths = get_image_paths(folder)
    hashes = compute_hashes(paths)
    duplicates = find_duplicates(hashes, threshold=threshold)
    print_duplicates(duplicates)
    return duplicates


def main():
    parser = argparse.ArgumentParser(description="Duplicate Image Finder (CLI)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_scan = subparsers.add_parser("scan", help="Scan folder for duplicate images")
    p_scan.add_argument("folder", help="Folder to scan")
    p_scan.add_argument("-t", "--threshold", type=int, default=HASH_DISTANCE_THRESHOLD, help="Hash distance threshold")

    p_move = subparsers.add_parser("move", help="Move duplicates to target folder")
    p_move.add_argument("folder", help="Folder to scan")
    p_move.add_argument("target", help="Destination folder")
    p_move.add_argument("-t", "--threshold", type=int, default=HASH_DISTANCE_THRESHOLD, help="Hash distance threshold")

    p_delete = subparsers.add_parser("delete", help="Delete duplicate images")
    p_delete.add_argument("folder", help="Folder to scan")
    p_delete.add_argument("-y", "--yes", action="store_true", help="Confirm deletion without prompt")
    p_delete.add_argument("-t", "--threshold", type=int, default=HASH_DISTANCE_THRESHOLD, help="Hash distance threshold")
    p_delete.add_argument("-m", "--manual-dir", help="Directory to move uncertain pairs for manual check (default: <folder>_manual_check)")
    p_delete.add_argument("-M", "--manual-threshold", type=int, default=2, help="Distance above which pairs are moved for manual check (default: 2)")

    args = parser.parse_args()

    if args.command == "scan":
        scan_folder(args.folder, args.threshold)
    elif args.command == "move":
        duplicates = scan_folder(args.folder, args.threshold)
        if not duplicates:
            sys.exit(0)
        move_duplicates(duplicates, args.target)
        print("Duplicates moved successfully.")
    elif args.command == "delete":
        duplicates = scan_folder(args.folder, args.threshold)
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


if __name__ == "__main__":
    main()
