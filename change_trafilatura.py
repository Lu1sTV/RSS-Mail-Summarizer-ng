import trafilatura
import os
import fileinput


def change_download_timeout(timeout_seconds):
    library_path = os.path.dirname(trafilatura.__file__)

    settings_file = os.path.join(library_path, "settings.cfg")
    print(f"Settings file path: {settings_file}")

    with fileinput.FileInput(settings_file, inplace=True) as file:
        for line in file:
            if "DOWNLOAD_TIMEOUT" in line:
                print(f"DOWNLOAD_TIMEOUT = {timeout_seconds}")
            else:
                print(line, end="")

    print("DOWNLOAD_TIMEOUT updated successfully!")



