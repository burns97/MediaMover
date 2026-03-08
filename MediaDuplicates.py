import argparse
import csv
import hashlib
import os
import sys
import tkinter as tk
from dataclasses import dataclass, field
from typing import Optional

try:
    from PIL import Image, ImageTk
except ImportError:
    sys.exit("Pillow is required: pip install Pillow")

try:
    import imagehash
except ImportError:
    imagehash = None

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except ImportError:
    pillow_heif = None

try:
    import exiftool
except ImportError:
    exiftool = None

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif",
    ".webp", ".heic", ".heif",
}
VIDEO_EXTENSIONS = {".mov", ".mp4", ".avi", ".mkv", ".wmv", ".m4v"}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

HEIC_EXTENSIONS = {".heic", ".heif"}

VIDEO_PLACEHOLDER_COLOR = "#336699"


@dataclass
class FileInfo:
    filepath: str
    file_size: int
    sha256: Optional[str] = None
    phash: Optional[str] = None
    dimensions: Optional[tuple] = None
    creation_date: Optional[str] = None


@dataclass
class DuplicateGroup:
    group_id: int
    match_type: str  # "exact", "near", "exact+near"
    files: list
    delete_indices: list = field(default_factory=list)


def main():
    parser = argparse.ArgumentParser(
        description="Detect and review duplicate photos and videos."
    )
    parser.add_argument("-s", "--srcdir", required=True, help="Directory to scan")
    parser.add_argument(
        "-n", "--dry-run", action="store_true",
        help="Show what would be deleted without removing files",
    )
    parser.add_argument(
        "-t", "--threshold", type=int, default=8,
        help="Hamming distance threshold for near-duplicate matching (default: 8)",
    )
    parser.add_argument(
        "--exact-only", action="store_true",
        help="Skip perceptual hashing, only find byte-identical files",
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="Write CSV report without launching interactive viewer",
    )
    args = parser.parse_args()

    src_dir = os.path.abspath(args.srcdir.strip())
    if not os.path.isdir(src_dir):
        sys.exit(f"Source directory does not exist: {src_dir}")

    if not args.exact_only and imagehash is None:
        print("WARNING: imagehash not installed. Falling back to --exact-only mode.")
        print("  Install with: pip install imagehash")
        args.exact_only = True

    print(f"Scanning: {src_dir}")
    file_list = scan_files(src_dir)
    print(f"Found {len(file_list)} media files")

    if pillow_heif is None and not args.exact_only:
        heic_count = sum(
            1 for fi in file_list
            if os.path.splitext(fi.filepath)[1].lower() in HEIC_EXTENSIONS
        )
        if heic_count > 0:
            print(f"WARNING: {heic_count} HEIC file(s) found but pillow-heif is not installed.")
            print("  HEIC files will only be checked for exact (byte-identical) duplicates.")
            print("  Near-duplicate detection for HEIC requires: pip install pillow-heif")

    if len(file_list) < 2:
        print("Not enough files to find duplicates.")
        return

    hash_all_files(file_list, args.exact_only)

    exact_groups = find_exact_duplicates(file_list)
    print(f"Found {len(exact_groups)} exact duplicate groups")

    near_groups = []
    if not args.exact_only:
        near_groups = find_near_duplicates(file_list, args.threshold)
        print(f"Found {len(near_groups)} near-duplicate groups")

    groups = merge_groups(exact_groups, near_groups)
    print(f"Total: {len(groups)} duplicate groups after merging")

    if not groups:
        print("No duplicates found.")
        return

    gather_metadata(groups)

    report_path = write_report(groups, src_dir)
    print(f"Report written to: {report_path}")

    if args.report_only:
        return

    app = DuplicateReviewApp(groups, args.dry_run)
    app.run()

    # Update report with decisions
    write_report(groups, src_dir)


def scan_files(src_dir):
    file_list = []
    for root, dirs, files in os.walk(src_dir, onerror=walk_error_handler):
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in MEDIA_EXTENSIONS:
                continue
            filepath = os.path.join(root, name)
            try:
                file_size = os.path.getsize(filepath)
            except OSError:
                continue
            file_list.append(FileInfo(filepath=filepath, file_size=file_size))
    return file_list


def walk_error_handler(exception_instance):
    print(f"Walk error: {exception_instance}")


def compute_sha256(filepath):
    h = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except OSError as e:
        print(f"Error hashing {filepath}: {e}")
        return None


def compute_perceptual_hash(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext in VIDEO_EXTENSIONS:
        return None
    if ext in HEIC_EXTENSIONS and pillow_heif is None:
        return None
    try:
        img = Image.open(filepath)
        return str(imagehash.average_hash(img))
    except Exception as e:
        print(f"Perceptual hash failed for {filepath}: {e}")
        return None


def hash_all_files(file_list, exact_only):
    total = len(file_list)
    for i, fi in enumerate(file_list, 1):
        if i % 100 == 0 or i == total:
            print(f"  Hashing {i}/{total}...", end="\r")
        fi.sha256 = compute_sha256(fi.filepath)
        if not exact_only:
            fi.phash = compute_perceptual_hash(fi.filepath)
    print()


def find_exact_duplicates(file_list):
    by_hash = {}
    for fi in file_list:
        if fi.sha256 is None:
            continue
        by_hash.setdefault(fi.sha256, []).append(fi)

    groups = []
    gid = 1
    for sha, files in by_hash.items():
        if len(files) >= 2:
            groups.append(DuplicateGroup(
                group_id=gid, match_type="exact", files=list(files)
            ))
            gid += 1
    return groups


def find_near_duplicates(file_list, threshold):
    hashable = [(i, fi) for i, fi in enumerate(file_list)
                if fi.phash is not None]
    if len(hashable) < 2:
        return []

    # Parse hashes
    parsed = []
    for idx, fi in hashable:
        try:
            h = imagehash.hex_to_hash(fi.phash)
            parsed.append((idx, fi, h))
        except Exception:
            continue

    # Union-Find
    parent = {idx: idx for idx, _, _ in parsed}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Pairwise comparison
    n = len(parsed)
    for i in range(n):
        for j in range(i + 1, n):
            idx_i, fi_i, h_i = parsed[i]
            idx_j, fi_j, h_j = parsed[j]
            # Skip if already exact duplicates (same SHA-256)
            if fi_i.sha256 == fi_j.sha256 and fi_i.sha256 is not None:
                continue
            dist = h_i - h_j
            if dist <= threshold:
                union(idx_i, idx_j)

    # Collect clusters
    clusters = {}
    for idx, fi, _ in parsed:
        root = find(idx)
        clusters.setdefault(root, []).append(fi)

    groups = []
    gid = 1
    for cluster_files in clusters.values():
        if len(cluster_files) >= 2:
            # Only include if not all same SHA-256 (those are exact dupes already)
            sha_set = {f.sha256 for f in cluster_files}
            if len(sha_set) > 1:
                groups.append(DuplicateGroup(
                    group_id=gid, match_type="near", files=list(cluster_files)
                ))
                gid += 1
    return groups


def merge_groups(exact_groups, near_groups):
    if not near_groups:
        for i, g in enumerate(exact_groups, 1):
            g.group_id = i
        return exact_groups

    # Build a map of filepath -> group indices for exact groups
    file_to_exact = {}
    for i, g in enumerate(exact_groups):
        for fi in g.files:
            file_to_exact[fi.filepath] = i

    merged = list(exact_groups)
    used_exact = set()

    for ng in near_groups:
        overlapping_exact = set()
        for fi in ng.files:
            if fi.filepath in file_to_exact:
                overlapping_exact.add(file_to_exact[fi.filepath])

        if not overlapping_exact:
            merged.append(ng)
        else:
            # Merge near group files into overlapping exact groups
            # Combine all into the first overlapping exact group
            target_idx = min(overlapping_exact)
            target = merged[target_idx]
            existing_paths = {fi.filepath for fi in target.files}

            for fi in ng.files:
                if fi.filepath not in existing_paths:
                    target.files.append(fi)
                    existing_paths.add(fi.filepath)

            # Merge other overlapping exact groups into target
            for idx in overlapping_exact:
                if idx != target_idx:
                    for fi in merged[idx].files:
                        if fi.filepath not in existing_paths:
                            target.files.append(fi)
                            existing_paths.add(fi.filepath)
                    used_exact.add(idx)

            target.match_type = "exact+near"

    # Remove absorbed groups
    final = [g for i, g in enumerate(merged) if i not in used_exact]
    for i, g in enumerate(final, 1):
        g.group_id = i
    return final


def gather_metadata(groups):
    all_files = []
    for g in groups:
        all_files.extend(g.files)

    if not all_files:
        return

    # Get dimensions from PIL where possible
    for fi in all_files:
        ext = os.path.splitext(fi.filepath)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            try:
                img = Image.open(fi.filepath)
                fi.dimensions = img.size
                img.close()
            except Exception:
                pass

    # Get creation dates from exiftool if available
    if exiftool is None:
        return

    date_tags = [
        "EXIF:DateTimeOriginal",
        "QuickTime:CreateDate",
        "EXIF:CreateDate",
    ]

    try:
        with exiftool.ExifToolHelper() as et:
            paths = [fi.filepath for fi in all_files]
            # Process in batches to avoid command line length limits
            batch_size = 50
            for start in range(0, len(paths), batch_size):
                batch_paths = paths[start:start + batch_size]
                batch_files = all_files[start:start + batch_size]
                try:
                    results = et.get_tags(batch_paths, date_tags)
                    for fi, meta in zip(batch_files, results):
                        for tag in date_tags:
                            if tag in meta and meta[tag]:
                                val = meta[tag]
                                if not isinstance(val, (bytes, bytearray)):
                                    fi.creation_date = str(val)
                                    break
                except Exception as e:
                    print(f"Metadata fetch error: {e}")
    except Exception as e:
        print(f"Could not start exiftool: {e}")


def write_report(groups, src_dir):
    report_path = os.path.join(src_dir, "duplicates_report.csv")
    with open(report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "group_id", "match_type", "filepath", "file_size",
            "dimensions", "creation_date", "sha256", "phash", "action",
        ])
        for g in groups:
            for i, fi in enumerate(g.files):
                if i in g.delete_indices:
                    action = "delete"
                elif g.delete_indices:
                    action = "keep"
                else:
                    action = ""
                writer.writerow([
                    g.group_id,
                    g.match_type,
                    fi.filepath,
                    fi.file_size,
                    f"{fi.dimensions[0]}x{fi.dimensions[1]}" if fi.dimensions else "",
                    fi.creation_date or "",
                    fi.sha256 or "",
                    fi.phash or "",
                    action,
                ])
    return report_path


def execute_deletions(filepaths, dry_run):
    deleted = 0
    failed = 0
    for fp in filepaths:
        if dry_run:
            print(f"  [DRY RUN] Would delete: {fp}")
            deleted += 1
        else:
            try:
                os.remove(fp)
                print(f"  Deleted: {fp}")
                deleted += 1
            except PermissionError:
                print(f"  FAILED (permission denied): {fp}")
                failed += 1
            except OSError as e:
                print(f"  FAILED ({e}): {fp}")
                failed += 1
    return deleted, failed


def format_size(size_bytes):
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"


class DuplicateReviewApp:
    THUMB_SIZE = 300
    BG_COLOR = "#2b2b2b"
    FG_COLOR = "#ffffff"
    SELECT_COLOR = "#4488cc"
    KEEP_COLOR = "#2d6a2d"
    DELETE_COLOR = "#8b2222"
    UNMARKED_COLOR = "#444444"

    def __init__(self, groups, dry_run):
        self.groups = groups
        self.dry_run = dry_run
        self.current_group_idx = 0
        self.selected_idx = 0
        self.thumb_images = []
        self.thumb_labels = []
        self.info_labels = []
        self.status_labels = []
        self.fullsize_mode = False
        self.fullsize_image = None
        self.fullsize_label = None
        self.fullsize_info = None

        self.root = tk.Tk()
        self.root.title("Duplicate Review")
        self.root.configure(bg=self.BG_COLOR)
        self.root.geometry("1200x700")

        self._build_ui()
        self._bind_keys()
        self._load_group()

    def _build_ui(self):
        # Header
        self.header = tk.Label(
            self.root, text="", font=("Helvetica", 14, "bold"),
            bg=self.BG_COLOR, fg=self.FG_COLOR, pady=8,
        )
        self.header.pack(fill=tk.X)

        # Main content area
        self.content_frame = tk.Frame(self.root, bg=self.BG_COLOR)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Grid frame (inside content)
        self.grid_frame = tk.Frame(self.content_frame, bg=self.BG_COLOR)
        self.grid_frame.pack(fill=tk.BOTH, expand=True)

        # Full-size frame (inside content, hidden initially)
        self.fullsize_frame = tk.Frame(self.content_frame, bg=self.BG_COLOR)
        self.fullsize_label = tk.Label(self.fullsize_frame, bg=self.BG_COLOR)
        self.fullsize_label.pack(fill=tk.BOTH, expand=True)
        self.fullsize_info = tk.Label(
            self.fullsize_frame, text="", font=("Helvetica", 11),
            bg="#333333", fg=self.FG_COLOR, pady=4,
        )
        self.fullsize_info.pack(fill=tk.X, side=tk.BOTTOM)

        # Help bar
        help_text = (
            "\u2190/\u2192 Select   K Keep   D Delete   A Keep-All   "
            "U Unmark   N Next   P Prev   Space Full-size   "
            "F/Enter Finish   Q Quit"
        )
        self.help_bar = tk.Label(
            self.root, text=help_text, font=("Helvetica", 10),
            bg="#333333", fg="#aaaaaa", pady=4,
        )
        self.help_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _bind_keys(self):
        self.root.bind("<Left>", lambda e: self._navigate(-1))
        self.root.bind("<Right>", lambda e: self._navigate(1))
        self.root.bind("<space>", lambda e: self._toggle_fullsize())
        self.root.bind("k", lambda e: self._mark_keep())
        self.root.bind("K", lambda e: self._mark_keep())
        self.root.bind("d", lambda e: self._mark_delete())
        self.root.bind("D", lambda e: self._mark_delete())
        self.root.bind("a", lambda e: self._keep_all())
        self.root.bind("A", lambda e: self._keep_all())
        self.root.bind("u", lambda e: self._unmark())
        self.root.bind("U", lambda e: self._unmark())
        self.root.bind("n", lambda e: self._next_group())
        self.root.bind("N", lambda e: self._next_group())
        self.root.bind("p", lambda e: self._prev_group())
        self.root.bind("P", lambda e: self._prev_group())
        self.root.bind("f", lambda e: self._finish())
        self.root.bind("F", lambda e: self._finish())
        self.root.bind("<Return>", lambda e: self._finish())
        self.root.bind("q", lambda e: self._quit())
        self.root.bind("Q", lambda e: self._quit())
        self.root.bind("<Escape>", lambda e: self._escape())
        for i in range(1, 10):
            self.root.bind(str(i), lambda e, idx=i - 1: self._quick_select(idx))
        self.root.bind("<Configure>", lambda e: self._on_resize(e))

    def _on_resize(self, event):
        if self.fullsize_mode and event.widget == self.root:
            self._show_fullsize_image()

    def _load_group(self):
        if self.fullsize_mode:
            self._exit_fullsize()

        group = self.groups[self.current_group_idx]
        self.selected_idx = 0

        self.header.config(
            text=f"Group {self.current_group_idx + 1} of {len(self.groups)} "
                 f"({group.match_type}) \u2014 {len(group.files)} files"
        )

        # Clear grid
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self.thumb_images.clear()
        self.thumb_labels.clear()
        self.info_labels.clear()
        self.status_labels.clear()

        # Build thumbnails
        for i, fi in enumerate(group.files):
            col_frame = tk.Frame(self.grid_frame, bg=self.BG_COLOR, padx=5, pady=5)
            col_frame.grid(row=0, column=i, sticky="n")

            # Thumbnail
            thumb_img = self._load_thumbnail(fi)
            self.thumb_images.append(thumb_img)

            thumb_label = tk.Label(
                col_frame, image=thumb_img, bg=self.UNMARKED_COLOR,
                borderwidth=3, relief="solid",
            )
            thumb_label.pack()
            thumb_label.bind("<Button-1>", lambda e, idx=i: self._click_select(idx))
            thumb_label.bind("<Double-Button-1>", lambda e, idx=i: self._double_click(idx))
            self.thumb_labels.append(thumb_label)

            # File info
            filename = os.path.basename(fi.filepath)
            if len(filename) > 30:
                filename = filename[:27] + "..."
            dim_str = f"{fi.dimensions[0]}x{fi.dimensions[1]}" if fi.dimensions else ""
            date_str = fi.creation_date or ""
            info_text = f"{filename}\n{format_size(fi.file_size)}\n{dim_str}\n{date_str}"
            info_label = tk.Label(
                col_frame, text=info_text, font=("Helvetica", 9),
                bg=self.BG_COLOR, fg=self.FG_COLOR, justify="center",
            )
            info_label.pack(pady=(4, 0))
            self.info_labels.append(info_label)

            # Status label
            status_label = tk.Label(
                col_frame, text="", font=("Helvetica", 10, "bold"),
                bg=self.BG_COLOR, fg=self.FG_COLOR,
            )
            status_label.pack()
            self.status_labels.append(status_label)

        self._update_selection()

    def _load_thumbnail(self, fi):
        ext = os.path.splitext(fi.filepath)[1].lower()
        if ext in VIDEO_EXTENSIONS:
            # Video placeholder
            img = Image.new("RGB", (self.THUMB_SIZE, self.THUMB_SIZE), VIDEO_PLACEHOLDER_COLOR)
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            draw.text(
                (self.THUMB_SIZE // 2, self.THUMB_SIZE // 2),
                "VIDEO", fill="white", anchor="mm",
            )
            return ImageTk.PhotoImage(img)
        try:
            img = Image.open(fi.filepath)
            img.thumbnail((self.THUMB_SIZE, self.THUMB_SIZE), Image.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            img = Image.new("RGB", (self.THUMB_SIZE, self.THUMB_SIZE), "#555555")
            from PIL import ImageDraw
            draw = ImageDraw.Draw(img)
            draw.text(
                (self.THUMB_SIZE // 2, self.THUMB_SIZE // 2),
                "ERROR", fill="red", anchor="mm",
            )
            return ImageTk.PhotoImage(img)

    def _update_selection(self):
        group = self.groups[self.current_group_idx]
        for i, label in enumerate(self.thumb_labels):
            if i in group.delete_indices:
                bg = self.DELETE_COLOR
                self.status_labels[i].config(text="DELETE", fg="#ff6666")
            elif group.delete_indices and i not in group.delete_indices:
                bg = self.KEEP_COLOR
                self.status_labels[i].config(text="KEEP", fg="#66ff66")
            else:
                bg = self.UNMARKED_COLOR
                self.status_labels[i].config(text="")

            if i == self.selected_idx:
                label.config(highlightbackground=self.SELECT_COLOR,
                             highlightthickness=3, bg=bg)
            else:
                label.config(highlightthickness=0, bg=bg)

        if self.fullsize_mode:
            self._update_fullsize_info()

    def _update_fullsize_info(self):
        group = self.groups[self.current_group_idx]
        fi = group.files[self.selected_idx]
        filename = os.path.basename(fi.filepath)
        size_str = format_size(fi.file_size)
        dim_str = f"{fi.dimensions[0]}x{fi.dimensions[1]}" if fi.dimensions else ""
        date_str = fi.creation_date or ""

        if self.selected_idx in group.delete_indices:
            status = "DELETE"
        elif group.delete_indices:
            status = "KEEP"
        else:
            status = ""

        info = f"[{self.selected_idx + 1}/{len(group.files)}]  {filename}  |  {size_str}"
        if dim_str:
            info += f"  |  {dim_str}"
        if date_str:
            info += f"  |  {date_str}"
        if status:
            info += f"  |  {status}"

        self.fullsize_info.config(text=info)

    def _navigate(self, direction):
        group = self.groups[self.current_group_idx]
        new_idx = self.selected_idx + direction
        if 0 <= new_idx < len(group.files):
            self.selected_idx = new_idx
            if self.fullsize_mode:
                self._show_fullsize_image()
            self._update_selection()

    def _click_select(self, idx):
        self.selected_idx = idx
        self._update_selection()

    def _double_click(self, idx):
        self.selected_idx = idx
        self._toggle_fullsize()

    def _quick_select(self, idx):
        group = self.groups[self.current_group_idx]
        if idx < len(group.files):
            self.selected_idx = idx
            if self.fullsize_mode:
                self._show_fullsize_image()
            self._update_selection()

    def _mark_keep(self):
        group = self.groups[self.current_group_idx]
        # Remove from delete list if present
        if self.selected_idx in group.delete_indices:
            group.delete_indices.remove(self.selected_idx)

        # 2-file group: marking one keep auto-marks the other delete
        if len(group.files) == 2:
            other = 1 - self.selected_idx
            if other not in group.delete_indices:
                group.delete_indices.append(other)

        self._update_selection()

    def _mark_delete(self):
        group = self.groups[self.current_group_idx]
        if self.selected_idx not in group.delete_indices:
            group.delete_indices.append(self.selected_idx)

            # 2-file group: marking one delete auto-marks the other keep
            if len(group.files) == 2:
                other = 1 - self.selected_idx
                if other in group.delete_indices:
                    group.delete_indices.remove(other)

        # Warn if all files marked for deletion
        if len(group.delete_indices) == len(group.files):
            self.header.config(
                text=self.header.cget("text").split(" \u26a0")[0] +
                     " \u26a0 WARNING: All files marked for deletion!"
            )

        self._update_selection()

    def _keep_all(self):
        group = self.groups[self.current_group_idx]
        group.delete_indices.clear()
        self._update_selection()
        self._next_group()

    def _unmark(self):
        group = self.groups[self.current_group_idx]
        if self.selected_idx in group.delete_indices:
            group.delete_indices.remove(self.selected_idx)
        # If this was the only non-deleted file in a 2-file group, also unmark the other
        if len(group.files) == 2 and not group.delete_indices:
            pass  # Both are now unmarked, which is fine
        self._update_selection()

    def _next_group(self):
        if self.fullsize_mode:
            return
        if self.current_group_idx < len(self.groups) - 1:
            self.current_group_idx += 1
            self._load_group()

    def _prev_group(self):
        if self.fullsize_mode:
            return
        if self.current_group_idx > 0:
            self.current_group_idx -= 1
            self._load_group()

    def _toggle_fullsize(self):
        if self.fullsize_mode:
            self._exit_fullsize()
        else:
            self._enter_fullsize()

    def _enter_fullsize(self):
        self.fullsize_mode = True
        self.grid_frame.pack_forget()
        self.fullsize_frame.pack(fill=tk.BOTH, expand=True)
        self._show_fullsize_image()
        self._update_selection()

    def _exit_fullsize(self):
        self.fullsize_mode = False
        self.fullsize_frame.pack_forget()
        self.grid_frame.pack(fill=tk.BOTH, expand=True)
        self.fullsize_image = None

    def _show_fullsize_image(self):
        group = self.groups[self.current_group_idx]
        fi = group.files[self.selected_idx]
        ext = os.path.splitext(fi.filepath)[1].lower()

        try:
            if ext in VIDEO_EXTENSIONS:
                w = max(self.fullsize_frame.winfo_width(), 400)
                h = max(self.fullsize_frame.winfo_height() - 30, 300)
                img = Image.new("RGB", (w, h), VIDEO_PLACEHOLDER_COLOR)
                from PIL import ImageDraw
                draw = ImageDraw.Draw(img)
                draw.text((w // 2, h // 2), "VIDEO", fill="white", anchor="mm")
            else:
                img = Image.open(fi.filepath)
                w = max(self.fullsize_frame.winfo_width(), 400)
                h = max(self.fullsize_frame.winfo_height() - 30, 300)
                img.thumbnail((w, h), Image.LANCZOS)

            self.fullsize_image = ImageTk.PhotoImage(img)
            self.fullsize_label.config(image=self.fullsize_image)
        except Exception as e:
            self.fullsize_label.config(text=f"Error loading image: {e}", image="")

        self._update_fullsize_info()

    def _escape(self):
        if self.fullsize_mode:
            self._exit_fullsize()
        else:
            self._quit()

    def _quit(self):
        self.root.destroy()

    def _finish(self):
        if self.fullsize_mode:
            return

        # Gather all files marked for deletion
        to_delete = []
        total_bytes = 0
        for g in self.groups:
            for idx in g.delete_indices:
                fi = g.files[idx]
                to_delete.append(fi.filepath)
                total_bytes += fi.file_size

        if not to_delete:
            from tkinter import messagebox
            messagebox.showinfo("Nothing to delete", "No files have been marked for deletion.")
            return

        # Check for groups where all files are marked
        all_delete_groups = []
        for g in self.groups:
            if len(g.delete_indices) == len(g.files) and g.delete_indices:
                all_delete_groups.append(g.group_id)

        from tkinter import messagebox
        msg = (
            f"Delete {len(to_delete)} files?\n"
            f"This will free {format_size(total_bytes)}."
        )
        if self.dry_run:
            msg += "\n\n(DRY RUN — files will NOT actually be deleted)"
        if all_delete_groups:
            msg += (
                f"\n\nWARNING: All files in group(s) {all_delete_groups} "
                f"are marked for deletion!"
            )

        if messagebox.askyesno("Confirm Deletion", msg):
            self.root.destroy()
            deleted, failed = execute_deletions(to_delete, self.dry_run)
            action = "would be deleted" if self.dry_run else "deleted"
            print(f"\n{deleted} files {action}, {failed} failed")
        # If no, stay in the viewer

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    main()
