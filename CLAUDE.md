# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MediaMover is a single-file Python CLI script that organizes photos and videos from a source directory into a date-based folder structure in a destination directory. It reads EXIF metadata (via PyExifTool/exiftool) to determine creation dates, falling back to filename patterns (`IMG_YYYYMMDD_HHMMSS`) and then parent folder names (`YYYY-MM-DD`).

## Running

```bash
# Copy mode (default)
python MediaMover.py -s <srcdir> -d <destdir>

# Move mode
python MediaMover.py --move -s <srcdir> -d <destdir>
```

## Dependencies

- Python 3
- [PyExifTool](https://sylikc.github.io/pyexiftool/index.html) (`pip install PyExifTool`)
- Phil Harvey's [exiftool](https://exiftool.org) executable must be on PATH (or placed alongside MediaMover.py on Windows)
- Install all deps: `pip install -r requirements.txt`

## Architecture

All logic lives in `MediaMover.py` (single file, no modules). Key flow:

1. **`main()`** - CLI argument parsing via `getopt` (`-c`/`--copy`, `-m`/`--move`, `-s`/`--srcdir`, `-d`/`--destdir`)
2. **`find_photos()`** - Walks source directory, skips `.ini`/`.db`/`.info` files, processes each file
3. **`findBestCreationDate()`** - Date resolution cascade: EXIF tags → filename pattern → parent folder name
4. **`move_media()`** - Classifies as Photo or Video (by extension: `.mov`/`.mp4`/`.avi`), copies/moves to destination
5. **`determine_media_dest_and_name()`** - Builds destination path: `<dest>/<Photo|Video>/<YYYY>/<MM - MonthName>/<YYYYMMDD-HHMMSS_originalname>`

EXIF tags checked in priority order: `EXIF:DateTimeOriginal`, `RIFF:DateTimeOriginal`, `QuickTime:CreateDate`, `Composite:GPSDateTime`, `EXIF:CreateDate`.

Output logs (`success_copy.txt` and `failed_copy.txt`) are written to the destination directory.

## Notes

- No test suite exists. There are `_test/` and `test/` directories but they are untracked scratch directories.
- The `move_video()` function (line 201) is dead code — not called anywhere. `move_media()` handles both photos and videos.
