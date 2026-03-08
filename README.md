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
