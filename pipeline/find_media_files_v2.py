#!/usr/bin/env python3
r"""
Script to find all media files (video and audio) in a given path and subfolders,
and output their information as JSON.

v2 change (logical change to parentfoldername):
    - parentfoldername is now the path of the folder containing the media file,
      expressed RELATIVE TO THE PARENT of root_path. This means the root folder
      name itself is included in the result.

    Example:
        root_path : \\quad\I\audiobooks\2 money\Jeffrey Fox - How to Make Big Money in Your Own Small Business
        abspath   : \\quad\I\audiobooks\2 money\Jeffrey Fox - How to Make Big Money in Your Own Small Business\disc 1
        v1 parentfoldername : disc 1
        v2 parentfoldername : Jeffrey Fox - How to Make Big Money in Your Own Small Business\disc 1
"""

import os
import json
import sys

VIDEO_EXTENSIONS = (".mp4", ".mkv", ".flv", ".f4v", ".mov")
AUDIO_EXTENSIONS = (".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wma", ".opus")
SUPPORTED_EXTENSIONS = VIDEO_EXTENSIONS + AUDIO_EXTENSIONS


def find_media_files(root_path, id_value):
    """
    Recursively find all supported media files (video and audio) in the given root path.

    Args:
        root_path (str): The absolute path to search
        id_value (str): The ID to include in each file's information

    Returns:
        list: List of dictionaries containing file information
    """
    media_files = []

    # The base folder that parentfoldername is measured against.
    # This is the PARENT of root_path, so that parentfoldername
    # includes the root folder name itself.
    root_parent = os.path.dirname(root_path)

    # Walk through all directories and subdirectories
    for dirpath, _, filenames in os.walk(root_path):
        for filename in filenames:
            if filename.lower().endswith(SUPPORTED_EXTENSIONS):
                # Extract the file name without extension
                medianame = os.path.splitext(filename)[0]

                # Absolute directory path
                abspath = os.path.abspath(dirpath)

                # Parent folder name: the folder containing the media file,
                # expressed relative to the parent of root_path. This keeps
                # the root folder name in the result (e.g.
                # "Jeffrey Fox - How to Make Big Money in Your Own Small Business\\disc 1").
                parentfoldername = os.path.relpath(dirpath, root_parent)

                file_info = {
                    "mp4name": medianame,   # kept for backward compatibility
                    "abspath": abspath,
                    "parentfoldername": parentfoldername,
                    "extension": os.path.splitext(filename)[1].lower(),
                    "id": id_value
                }

                media_files.append(file_info)

    return media_files


def main():
    """Main function to handle command line arguments and output JSON."""
    if len(sys.argv) != 3:
        print("Usage: python find_media_files_v2.py <absolute_path> <ID>")
        sys.exit(1)

    root_path = sys.argv[1]
    id_value = sys.argv[2]

    if not os.path.exists(root_path):
        print(f"Error: Path '{root_path}' does not exist.")
        sys.exit(1)

    if not os.path.isabs(root_path):
        print(f"Error: Path '{root_path}' is not an absolute path.")
        sys.exit(1)

    media_files = find_media_files(root_path, id_value)

    print(json.dumps(media_files, indent=2))


if __name__ == "__main__":
    main()
