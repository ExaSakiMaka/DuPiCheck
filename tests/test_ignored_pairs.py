import sqlite3
import tempfile
from main import list_ignored_pairs, remove_ignored_pair


def test_list_and_remove():
    with tempfile.TemporaryDirectory() as td:
        db_path = f"{td}/test.db"
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE ignored_pairs (p1 TEXT, p2 TEXT)")
        cur.execute("INSERT INTO ignored_pairs (p1,p2) VALUES (?,?)", ("/a/1.jpg", "/b/2.jpg"))
        cur.execute("INSERT INTO ignored_pairs (p1,p2) VALUES (?,?)", ("/c/3.jpg", "/d/4.jpg"))
        conn.commit()
        conn.close()

        pairs = list_ignored_pairs(db_path)
        assert len(pairs) == 2
        assert pairs[0] == ("/a/1.jpg", "/b/2.jpg")

        ok = remove_ignored_pair(db_path, "/a/1.jpg", "/b/2.jpg")
        assert ok
        pairs = list_ignored_pairs(db_path)
        assert len(pairs) == 1

        ok2 = remove_ignored_pair(db_path, "/x/not.jpg", "/y/no.jpg")
        assert not ok2
