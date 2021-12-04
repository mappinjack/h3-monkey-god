import os
import requests


FRICTION_SURFACE_URL = "https://malariaatlas.org/geoserver/ows?service=CSW&version=2.0.1&request=DirectDownload&ResourceId=Explorer:2015_friction_surface_v1_Decompressed"
ZIP_FILE_NAME = "friction_surface.zip"


def _friction_surface_exists(file_name=ZIP_FILE_NAME):
    """Check whether the friction surface already exists"""
    this_dir = os.path.dirname(os.path.realpath(__file__))
    files = os.listdir(os.path.join(this_dir, "data"))
    if file_name in files:
        return True
    return False


def get_friction_surface(url=FRICTION_SURFACE_URL, download_location=ZIP_FILE_NAME):
    """Download friction surface to a specific directory"""
    if _friction_surface_exists():
        print("Friction surface is already downloaded")
        return
    print("Downloading friction surface")
    with requests.get(url, stream=True) as r:
        with open(download_location, "wb") as f:
            total_downloaded = 0
            for data in r.iter_content(chunk_size=4096):
                total_downloaded += len(data)
                pretty_downloaded = total_downloaded / 1024 / 1024
                f.write(data)
                if pretty_downloaded % 10 == 0:
                    print(f"Downloaded {pretty_downloaded} MB of approx 710 MB")
    print("Success")


if __name__ == "__main__":
    get_friction_surface(FRICTION_SURFACE_URL, ZIP_FILE_NAME)
    # Download data to this folder
