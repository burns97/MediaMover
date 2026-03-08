import argparse
import os
import shutil
from datetime import datetime
import exiftool


def main():
    parser = argparse.ArgumentParser(description="Organize media files by date.")
    parser.add_argument("-s", "--srcdir", required=True, help="Source directory")
    parser.add_argument("-d", "--destdir", required=True, help="Destination directory")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-c", "--copy", action="store_true", help="Copy files (default)")
    group.add_argument("-m", "--move", action="store_true", help="Move files")
    parser.add_argument("-n", "--dry-run", action="store_true",
                        help="Show what would happen without copying/moving files")
    args = parser.parse_args()

    src_dir = args.srcdir.strip()
    dest_dir = args.destdir.strip()
    move_files = args.move
    dry_run = args.dry_run

    print("Source directory:", src_dir)
    print("Destination directory:", dest_dir)
    if dry_run:
        print("*** DRY RUN — no files will be copied or moved ***")
    action = "Moving" if move_files else "Copying"
    print(f"{action} files from {src_dir} to {dest_dir}")

    find_photos(src_dir, dest_dir, move_files, dry_run)


def find_photos(source_dir, dest_dir, move_files, dry_run):
    os.makedirs(dest_dir, exist_ok=True)

    counts = {"success": 0, "skipped": 0, "failed": 0}

    with open(os.path.join(dest_dir, "success_copy.txt"), "w") as fo_success, \
         open(os.path.join(dest_dir, "failed_copy.txt"), "w") as fo_failed:

        with exiftool.ExifToolHelper() as et:
            for root, dirs, files in os.walk(source_dir, topdown=True, onerror=walk_error_handler):
                print("Files in " + root)
                for name in files:
                    if name.endswith("ini") or name.endswith("db") or name.endswith("info"):
                        continue
                    curr_img_path = os.path.join(root, name)
                    print(curr_img_path)

                    try:
                        media_date = find_best_creation_date(curr_img_path, et)

                        if media_date is not None:
                            result = move_media(dest_dir, curr_img_path, media_date, move_files, dry_run)
                        else:
                            result = "failed"

                    except Exception as e:
                        print(f"--- Error processing file: {e}")
                        result = "failed"

                    if result == "success":
                        counts["success"] += 1
                        fo_success.write(curr_img_path + "\n")
                    elif result == "skipped":
                        counts["skipped"] += 1
                        fo_success.write(curr_img_path + " [skipped - already exists]\n")
                    else:
                        counts["failed"] += 1
                        fo_failed.write(curr_img_path + "\n")

                print("-----")
                print("")

    action = "moved" if move_files else "copied"
    if dry_run:
        action = "would be " + action
    print(f"Done: {counts['success']} {action}, {counts['skipped']} skipped, {counts['failed']} failed")


def walk_error_handler(exception_instance):
    print(f"Walk error: {exception_instance}")


def find_best_creation_date(media_path, et):
    date_tags = [
        "EXIF:DateTimeOriginal",
        "RIFF:DateTimeOriginal",
        "QuickTime:CreateDate",
        "Composite:GPSDateTime",
        "EXIF:CreateDate",
    ]
    try:
        metadata = et.get_tags(media_path, date_tags)
    except UnicodeDecodeError as err:
        print(f"Encoding issue with file {media_path}: {err}")
        return None
    except Exception as err:
        print(err)
        return None

    for tag_name in date_tags:
        media_date = check_for_date_in_tags(metadata, tag_name)
        if media_date is not None:
            print(f"using {tag_name} of {media_date} for value of media date")
            return media_date

    # No useful information in the EXIF, next check the filename
    # e.g. IMG_20140830_163939.JPG
    try:
        root_dir, filename = os.path.split(media_path)
        filename_date = datetime.strptime(filename[:19], "IMG_%Y%m%d_%H%M%S")
        print(f"using date from filename of {filename_date} for value of media date")
        return filename_date
    except Exception:
        pass

    # As a last resort, take a date from the folder where this image is found
    root_dir, last_dir = os.path.split(os.path.dirname(media_path))
    try:
        media_date = datetime.strptime(last_dir, "%Y-%m-%d")
    except ValueError:
        return None

    print(f"using date from containing folder of {media_date} for value of media date")
    return media_date


def check_for_date_in_tags(tag_data, date_name):
    try:
        if date_name in tag_data[0]:
            exif_date = tag_data[0][date_name]
            if isinstance(exif_date, (bytes, bytearray)):
                print(f"Skipping binary data in field {date_name}")
                return None
            return datetime.strptime(exif_date, "%Y:%m:%d %H:%M:%S")
    except Exception as err:
        print(f"Error processing tag {date_name}: {err}")
        return None


def move_media(dest_dir, media_path, media_date, move_files, dry_run):
    if media_path.lower().endswith("mov") or media_path.lower().endswith("mp4") or media_path.lower().endswith("avi"):
        media_type = "Video"
    else:
        media_type = "Photo"

    dest_dir = os.path.join(dest_dir, media_type)
    media_dest_dir, media_dest_name = determine_media_dest_and_name(dest_dir, media_path, media_date)
    media_dest_full_path = os.path.join(media_dest_dir, media_dest_name)

    action = "Moving" if move_files else "Copying"
    print(f"{action} {media_type} from {media_path} to {media_dest_full_path}")

    if os.path.exists(media_dest_full_path):
        print(f"*** File {media_dest_full_path} already exists. Skipping.")
        return "skipped"

    if dry_run:
        return "success"

    if not os.path.exists(media_dest_dir):
        os.makedirs(media_dest_dir)
    if move_files:
        shutil.move(media_path, media_dest_full_path)
    else:
        shutil.copy2(media_path, media_dest_full_path)
    return "success"


def determine_media_dest_and_name(dest_dir, media_path, media_date):
    new_dest_dir = os.path.join(dest_dir, str(media_date.year), media_date.strftime("%m - %B"))
    path, orig_filename = os.path.split(media_path)
    new_filename = media_date.strftime("%Y%m%d-%H%M%S_") + orig_filename
    return new_dest_dir, new_filename


if __name__ == "__main__":
    main()
