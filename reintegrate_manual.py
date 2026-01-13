#!/usr/bin/env python3
"""Restore manually-sorted pair folders back to original locations and optionally mark them ignored in the DB.

Usage:
  reintegrate_manual.py /path/to/manual_dir [--db-file /path/to/db] [--dry-run] [--no-remove] [--no-mark]

Examples:
  ./reintegrate_manual.py test/manual_check --db-file test/.dupicheck.db
"""
import os
import argparse
from main import reintegrate_manual


def main():
    p = argparse.ArgumentParser(description="Reintegrate manual pair folders into original locations")
    p.add_argument("manual_dir", help="Manual-check folder containing pair_XXX subfolders")
    p.add_argument("--db-file", help="DB file to update (default: <manual_dir>/../.dupicheck.db)")
    p.add_argument("--dry-run", action="store_true", help="Show what would be done without moving files")
    p.add_argument("--no-remove", action="store_true", help="Do not remove empty pair folders after restoring")
    p.add_argument("--no-mark", action="store_true", help="Do not mark restored pairs as ignored in DB")

    args = p.parse_args()

    db_file = args.db_file if args.db_file else os.path.join(os.path.dirname(args.manual_dir), ".dupicheck.db")
    res = reintegrate_manual(args.manual_dir, db_file=db_file, dry_run=args.dry_run, remove_empty=not args.no_remove, mark_ignored_if_both=not args.no_mark)
    if res is None:
        return
    print("Done.")

if __name__ == '__main__':
    main()
