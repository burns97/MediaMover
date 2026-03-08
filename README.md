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
- `photo.jpg` → `photo_[DZ2.0].jpg` (digital zoom with ratio)
- `photo_[SS][DZ2.0].jpg` (both)

A `review_report.csv` file is written to the source directory with details on every scanned file.

Run `python MediaReview.py --help` for full option details.
