import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from main import get_image_paths, compute_hashes, find_duplicates, move_duplicates, delete_duplicates, HASH_DISTANCE_THRESHOLD


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
        tk.Button(top, text="Delete", command=self.delete).pack(side=tk.LEFT, padx=5)

        self.output = ScrolledText(root, height=20, width=80)
        self.output.pack(padx=10, pady=10)

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

        self.output.insert(tk.END, "Scanning...\n")
        paths = get_image_paths(self.folder)
        hashes = compute_hashes(paths)
        self.duplicates = find_duplicates(hashes, threshold=thr)

        if not self.duplicates:
            self.output.insert(tk.END, "No duplicates found.\n")
            return

        for orig, dup, dist in self.duplicates:
            self.output.insert(tk.END, f"\nORIGINAL: {orig}\nDUPLICATE: {dup}\nDistance: {dist}\n")

        self.output.insert(tk.END, f"\nFound {len(self.duplicates)} duplicates.\n")

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
        if messagebox.askyesno("Confirm", "Are you sure you want to DELETE duplicates?"):
            delete_duplicates(self.duplicates)
            messagebox.showinfo("Done", "Duplicates deleted")


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
