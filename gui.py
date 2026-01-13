import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from tkinter import ttk
import threading

from main import get_image_paths, compute_hashes, find_duplicates, move_duplicates, delete_with_checks, HASH_DISTANCE_THRESHOLD


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Duplicate Image Finder (GUI)")

        self.folder = ""

        top = tk.Frame(root)
        top.pack(padx=10, pady=10)

        tk.Button(top, text="Select Folder", command=self.select_folder).pack(side=tk.LEFT, padx=5)
        tk.Label(top, text="Threshold:").pack(side=tk.LEFT)
        self.threshold_var = tk.StringVar(value=str(HASH_DISTANCE_THRESHOLD))
        tk.Entry(top, textvariable=self.threshold_var, width=5).pack(side=tk.LEFT, padx=5)
        tk.Button(top, text="Scan", command=self.scan).pack(side=tk.LEFT, padx=5)
        tk.Button(top, text="Move", command=self.move).pack(side=tk.LEFT, padx=5)
        tk.Label(top, text="Manual M:" ).pack(side=tk.LEFT)
        self.manual_var = tk.StringVar(value="2")
        tk.Entry(top, textvariable=self.manual_var, width=3).pack(side=tk.LEFT, padx=5)
        tk.Button(top, text="Delete", command=self.delete).pack(side=tk.LEFT, padx=5)

        self.output = ScrolledText(root, height=14, width=80)
        self.output.pack(padx=10, pady=10)

        # progress widgets
        prog_frame = tk.Frame(root)
        prog_frame.pack(fill=tk.X, padx=10)
        tk.Label(prog_frame, text="Progress:").pack(side=tk.LEFT)
        self.progress_var = tk.DoubleVar(value=0)
        self.progressbar = ttk.Progressbar(prog_frame, variable=self.progress_var, maximum=100)
        self.progressbar.pack(fill=tk.X, expand=True, side=tk.LEFT, padx=10)
        self.current_label = tk.Label(prog_frame, text="Idle")
        self.current_label.pack(side=tk.LEFT)

        self.duplicates = []

    def select_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.folder = d
            self.output.insert(tk.END, f"Selected folder: {self.folder}\n")

    def scan(self):
        if not self.folder:
            messagebox.showerror("Error", "Select a folder first")
            return
        try:
            thr = int(self.threshold_var.get())
        except ValueError:
            messagebox.showerror("Error", "Threshold must be an integer")
            return

        self._set_busy(True)
        self.output.insert(tk.END, "Scanning...\n")

        def progress_cb(index, total, path):
            pct = (index / total) * 100 if total else 0
            self.root.after(0, lambda: self._update_progress(pct, os.path.basename(path)))

        def worker():
            paths = get_image_paths(self.folder)
            hashes = compute_hashes(paths, progress_callback=progress_cb)
            self.duplicates = find_duplicates(hashes, threshold=thr)

            def finish():
                if not self.duplicates:
                    self.output.insert(tk.END, "No duplicates found.\n")
                else:
                    for orig, dup, dist in self.duplicates:
                        self.output.insert(tk.END, f"\nORIGINAL: {orig}\nDUPLICATE: {dup}\nDistance: {dist}\n")
                    self.output.insert(tk.END, f"\nFound {len(self.duplicates)} duplicates.\n")
                self._set_busy(False)
                self._update_progress(0, "Idle")

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _set_busy(self, busy=True):
        for child in self.root.winfo_children():
            if isinstance(child, tk.Button):
                child.config(state=(tk.DISABLED if busy else tk.NORMAL))

    def _update_progress(self, percent, filename):
        self.progress_var.set(percent)
        self.current_label.config(text=f"{percent:.0f}% - {filename}")

    def move(self):
        if not self.duplicates:
            messagebox.showinfo("Info", "No duplicates to move. Scan first.")
            return
        target = filedialog.askdirectory(title="Select destination folder")
        if target:
            move_duplicates(self.duplicates, target)
            messagebox.showinfo("Done", "Duplicates moved successfully")

    def delete(self):
        if not self.duplicates:
            messagebox.showinfo("Info", "No duplicates to delete. Scan first.")
            return
        if not messagebox.askyesno("Confirm", "Are you sure you want to DELETE duplicates?"):
            return
        target = filedialog.askdirectory(title="Select manual-check destination (files with M>manual_threshold will be moved there)")
        if not target:
            messagebox.showinfo("Info", "No manual folder selected. Aborted.")
            return
        try:
            manual_thr = int(self.manual_var.get())
        except ValueError:
            messagebox.showerror("Error", "Manual threshold must be an integer")
            return
        res = delete_with_checks(self.duplicates, target, manual_threshold=manual_thr)
        pairs = len(res.get('moved_pairs', []))
        files = len(res.get('moved', []))
        messagebox.showinfo("Done", f"Deleted: {len(res.get('deleted', []))}, Moved for manual: {pairs} pairs ({files} files)")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
