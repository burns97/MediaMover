# MediaMover

## Intro
Just a simple Python script I created to help learn Python.

I have multiple sources of digital images captured in my house and was looking for a way to automatically rename and move those files into a common location.

## Dependency:
This script uses a python module [PyExifTool](https://sylikc.github.io/pyexiftool/index.html) which is a wrapper for the executable Phil Harvey's [exiftool](https://exiftool.org).

MediaMover needs to be able to locate the exiftool executable. For simplicity on Windows, I just placed a copy of it in the same directory as `MediaMover.py`. If you are running on Linux or Mac, it is probably easier to install it via your favorite package manager.

## Usage

```bash
# Copy mode (default)
python MediaMover.py -s <srcdir> -d <destdir>

# Move mode
python MediaMover.py --move -s <srcdir> -d <destdir>

# Dry run — see what would happen without copying or moving
python MediaMover.py --dry-run -s <srcdir> -d <destdir>
```

Run `python MediaMover.py --help` for full option details.

## MediaReview — Photo Flagging

`MediaReview.py` scans a directory of photos and flags screenshots and digitally-zoomed (pinch-to-zoom) images. It renames flagged files with codes and generates a CSV summary report.

### Detection

- **Screenshots** — identified by the absence of camera EXIF tags (LensModel, FNumber, ISO, ShutterSpeedValue)
- **Digital zoom** — identified by `EXIF:DigitalZoomRatio` > 1.0 (pinch-to-zoom beyond the optical lens)

### Usage

```bash
# Dry run — see what would be flagged without renaming
python MediaReview.py --dry-run -s <srcdir>

# Flag and rename files
python MediaReview.py -s <srcdir>
```

Flagged files are renamed with codes before the extension:
- `photo.jpg` → `photo_[SS].jpg` (screenshot)
- `photo.jpg` → `photo_[DZ].jpg` (digital zoom)
- `photo_[SS][DZ].jpg` (both)

A `review_report.csv` file is written to the source directory with details on every scanned file.

Run `python MediaReview.py --help` for full option details.

## MediaDuplicates — Duplicate Photo Detection & Review

`MediaDuplicates.py` scans a directory for duplicate photos and videos using SHA-256 hashing (exact copies) and perceptual hashing (visually similar images). It provides an interactive tkinter viewer to review and selectively delete duplicates.

### Usage

```bash
# Full scan with interactive viewer
python MediaDuplicates.py -s <srcdir>

# Report only — write CSV without launching viewer
python MediaDuplicates.py --report-only -s <srcdir>

# Exact duplicates only (skip perceptual hashing)
python MediaDuplicates.py --exact-only -s <srcdir>

# Dry run — review and mark files, but don't actually delete
python MediaDuplicates.py --dry-run -s <srcdir>

# Adjust perceptual hash sensitivity (default: 8)
python MediaDuplicates.py -t 5 -s <srcdir>
```

The interactive viewer shows thumbnails side-by-side with file metadata. Use keyboard shortcuts to mark files as KEEP or DELETE, then press F to execute deletions. Press Space to toggle full-size view of any image.

A `duplicates_report.csv` file is written to the source directory with details on every duplicate group.

Run `python MediaDuplicates.py --help` for full option details.
