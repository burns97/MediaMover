import argparse
import csv
import os
import re
import exiftool


REVIEW_TAGS = [
    "EXIF:LensModel",
    "EXIF:FNumber",
    "EXIF:ISO",
    "EXIF:ShutterSpeedValue",
    "EXIF:DigitalZoomRatio",
    "EXIF:FocalLength",
]

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff", ".tif", ".webp"}


def main():
    parser = argparse.ArgumentParser(description="Flag screenshots and digitally-zoomed photos.")
    parser.add_argument("-s", "--srcdir", required=True, help="Directory to scan")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="Show what would be flagged without renaming files")
    args = parser.parse_args()

    src_dir = args.srcdir.strip()
    dry_run = args.dry_run

    if not os.path.isdir(src_dir):
        print(f"Error: source directory '{src_dir}' does not exist.")
        return

    if dry_run:
        print("*** DRY RUN — no files will be renamed ***")

    review_photos(src_dir, dry_run)


def review_photos(src_dir, dry_run):
    results = []
    counts = {"scanned": 0, "screenshots": 0, "digital_zoom": 0, "clean": 0}

    with exiftool.ExifToolHelper() as et:
        for root, dirs, files in os.walk(src_dir):
            for name in files:
                ext = os.path.splitext(name)[1].lower()
                if ext not in IMAGE_EXTENSIONS:
                    continue

                filepath = os.path.join(root, name)

                # Skip already-flagged files
                if "_[SS]" in name or "_[DZ" in name:
                    continue

                counts["scanned"] += 1

                try:
                    metadata = et.get_tags(filepath, REVIEW_TAGS)
                except Exception as e:
                    print(f"Error reading EXIF for {filepath}: {e}")
                    continue

                tags = metadata[0] if metadata else {}

                screenshot = is_screenshot(tags)
                zoom_ratio = get_digital_zoom_ratio(tags)

                flags = []
                if screenshot:
                    flags.append("SS")
                    counts["screenshots"] += 1
                if zoom_ratio is not None:
                    flags.append("DZ")
                    counts["digital_zoom"] += 1

                renamed_to = ""
                if flags:
                    new_name = build_flagged_name(name, flags)
                    new_path = os.path.join(root, new_name)
                    renamed_to = new_name
                    if dry_run:
                        print(f"  Would rename: {name} -> {new_name}")
                    else:
                        os.rename(filepath, new_path)
                        print(f"  Renamed: {name} -> {new_name}")
                else:
                    counts["clean"] += 1

                results.append({
                    "filepath": filepath,
                    "screenshot": screenshot,
                    "digital_zoom_ratio": zoom_ratio if zoom_ratio else "",
                    "lens_model": tags.get("EXIF:LensModel", ""),
                    "focal_length": tags.get("EXIF:FocalLength", ""),
                    "renamed_to": renamed_to,
                })

    # Write report CSV
    report_path = os.path.join(src_dir, "review_report.csv")
    with open(report_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "filepath", "screenshot", "digital_zoom_ratio",
            "lens_model", "focal_length", "renamed_to",
        ])
        writer.writeheader()
        writer.writerows(results)
    print(f"\nReport written to {report_path}")

    print(f"Done: {counts['scanned']} scanned, {counts['screenshots']} screenshots, "
          f"{counts['digital_zoom']} digitally zoomed, {counts['clean']} clean")


def is_screenshot(tags):
    camera_tags = ["EXIF:LensModel", "EXIF:FNumber", "EXIF:ISO", "EXIF:ShutterSpeedValue"]
    return not any(tag in tags for tag in camera_tags)


def get_digital_zoom_ratio(tags):
    ratio = tags.get("EXIF:DigitalZoomRatio")
    if ratio is not None:
        try:
            ratio = float(ratio)
            if ratio > 1.0:
                return ratio
        except (ValueError, TypeError):
            pass
    return None


def build_flagged_name(original_name, flags):
    base, ext = os.path.splitext(original_name)
    flag_str = "".join(f"_[{f}]" for f in flags)
    return base + flag_str + ext


if __name__ == "__main__":
    main()
