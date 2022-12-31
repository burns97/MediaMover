import getopt
import os
import shutil
import sys
from datetime import datetime
import exiftool


def main(argv):
    srcDir = ""
    destDir = ""
    move_files = False
    try:
      opts, args = getopt.getopt(argv, "hcms:d:", ["copy", "move", "srcdir=", "destdir="])
    except getopt.GetoptError:
      print("MediaMover.py -s <srcdir> -d <destdir>")
      sys.exit(2)
    for opt, arg in opts:
      if opt == "-h":
         print("test.py -s <srcdir> -d <destdir>")
         sys.exit()
      elif opt in ("-c", "--copy"):
          move_files = False
      elif opt in ("-m", "--move"):
          move_files = True
      elif opt in ("-s", "--srcdir"):
          srcDir = arg.strip()
      elif opt in ("-d", "--destdir"):
          destDir = arg.strip()
   
    print("Source directory:", srcDir)
    print("Destination directory:", destDir)
    if move_files:
        print("Moving files from " + srcDir + " to " + destDir)
    else:
        print("Copying files from " + srcDir + " to " + destDir)

    find_photos(srcDir, destDir, move_files)


def get_field(exif, field):
    for (k, v) in exif.iteritems():
        # t = TAGS.get(k)
        if k == field:
            return v


def find_photos(sourceDir, destDir, move_files):
    if os.path.isdir(destDir):
        if not os.path.exists(destDir):
            os.makedirs(destDir)

    fo_success = open(os.path.join(destDir, "success_copy.txt"), "w")
    fo_failed = open(os.path.join(destDir, "failed_copy.txt"), "w")

    for root, dirs, files in os.walk(sourceDir, topdown=True, onerror=walk_error_handler):
        print("Files in " + root)
        for name in files:
            if name.endswith("ini") or name.endswith("db") or name.endswith("info"):
                continue
            currImgPath = os.path.join(root, name)
            print(currImgPath)

            # Let's see if this is an image or video file with exif data
            try:
                media_date = findBestCreationDate(currImgPath)

                if media_date is not None:
                    successful_move = move_media(destDir, currImgPath, media_date, move_files)
                else:
                    successful_move = False

            except:
                print("--- No EXIF data.  May not be a photo.")
                successful_move = False

            if successful_move:
                fo_success.write(currImgPath + "\n")
            else:
                fo_failed.write(currImgPath + "\n")

        print("-----")
        print("")

    fo_success.close()
    fo_failed.close()


def walk_error_handler(exception_instance):
    print("uh-oh! " + exception_instance)


def findBestCreationDate(mediaPath):
    # Dig through the metadata in the media file to find a suitable creation date

    try:
        with exiftool.ExifToolHelper() as et:
            metadata = et.get_metadata(mediaPath)
    except Exception as err:
        print(err)

    dateTags = ["EXIF:DateTimeOriginal", "RIFF:DateTimeOriginal", "QuickTime:CreateDate", "Composite:GPSDateTime", "EXIF:CreateDate"]

    for tagName in dateTags:
        media_date = checkForDateInTags(metadata, tagName)
        if media_date is not None:
            print ("using " + tagName + " of " + str(media_date) + " for value of media date")
            return media_date

    # No useful information in the EXIF, next check the filename
    # e.g. IMG_20140830_163939.JPG
    filenameDate = None
    try:
        root_dir, filename = os.path.split(mediaPath)
        filenameDate = datetime.strptime(filename[:19], "IMG_%Y%m%d_%H%M%S")
        print ("using date from filename of " + str(filenameDate) + " for value of media date")
        return filenameDate
    except Exception:
        pass

    # We were unable to find anything useful in the EXIF data or filename
    # As a last resort, let's take a date from the folder where this image is found
    root_dir, last_dir = os.path.split(os.path.dirname(mediaPath))
    media_date = datetime.strptime(last_dir, "%Y-%m-%d")

    if media_date is not None:
        print ("using date from containing folder of " + str(media_date) + " for value of media date")
        return media_date

    return None

def checkForDateInTags(tagData, dateName):
    exifDate = None
    try:
        #if dateName in tagData[0].keys():
        exifDate = tagData[0][dateName]

    except Exception:
        return None

    if exifDate is not None:
        try:
            mediaDate = datetime.strptime(exifDate, "%Y:%m:%d %H:%M:%S")
        except Exception as err:
            print(err)

        return mediaDate

def move_media(dest_dir, media_path, media_date, move_files):
    # See if this is a video file and handle it first
    if media_path.lower().endswith("mov") or media_path.lower().endswith("mp4") or media_path.lower().endswith("avi"):
        media_type = "Video"
    else:
        media_type = "Photo"

    dest_dir = os.path.join(dest_dir, media_type)
    media_dest_dir, media_dest_name = determine_media_dest_and_name(dest_dir, media_path, media_date)
    media_dest_full_path = os.path.join(media_dest_dir, media_dest_name)
    if move_files:
        print("Moving " + media_type + " from " + media_path + " to " + media_dest_full_path)
    else:
        print("Copying " + media_type + " from " + media_path + " to " + media_dest_full_path)
    if not os.path.exists(media_dest_dir):
        os.makedirs(media_dest_dir)
    if not os.path.exists(media_dest_full_path):
        if move_files:
            shutil.move(media_path, media_dest_full_path)
        else:
            shutil.copy2(media_path, media_dest_full_path)
        return True
    else:
        print("*** File " + media_dest_full_path + " already exists.")
        return True


def determine_media_dest_and_name(destDir, mediaPath, mediaDate):
    newDestDir = os.path.join(destDir, str(mediaDate.year), mediaDate.strftime("%m - %B"))
    path, orig_filename = os.path.split(mediaPath)
    new_filename = mediaDate.strftime("%Y%m%d-%H%M%S_") + orig_filename
    return newDestDir, new_filename


def move_video(destDir, videoPath):
    # Tease out a date to use for the video
    # P:\2012\2012-08-13\075.MOV
    pathParts = videoPath.split("\\")
    videoDate = pathParts[len(pathParts)-2]
    videoDestDir, videoDestName = determine_media_dest_and_name(destDir, videoPath, videoDate)
    videoDestFullPath = os.path.join(videoDestDir, videoDestName)
    print("Moving video from " + videoPath + " to " + videoDestFullPath)
    if not os.path.exists(videoDestDir):
        os.makedirs(videoDestDir)
    if not os.path.exists(videoDestFullPath):
        shutil.copy2(videoPath, videoDestFullPath)
        return True
    else:
        print("*** File " + videoDestFullPath + " already exists.")
        return True

if __name__ == "__main__":
   main(sys.argv[1:])
