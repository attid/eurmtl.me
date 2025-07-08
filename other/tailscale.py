import re
import asyncio
import os
from packaging.version import Version, InvalidVersion

from other.config_reader import start_path
from other.web_tools import http_session_manager, WebResponse # Assuming http_session_manager is in web_tools

PACKAGES_URL = "https://pkgs.tailscale.com/stable/ubuntu/dists/focal/main/binary-amd64/Packages"
BASE_DOWNLOAD_URL = "https://pkgs.tailscale.com/stable/ubuntu/"

def normalize(v):
    # Пропускаем версии, которые packaging не поддерживает
    try:
        return Version(v)
    except InvalidVersion:
        return None

async def get_latest_version_package() -> str:
    STATIC_DIR = start_path  + "/static"
    # Ensure static directory exists
    if not os.path.exists(STATIC_DIR):
        os.makedirs(STATIC_DIR)

    packages_response: WebResponse = await http_session_manager.get_web_request("GET", PACKAGES_URL, return_type="text")
    if packages_response.status != 200:
        raise RuntimeError(f"Failed to fetch packages list: {packages_response.status} {packages_response.data}")
    
    content = packages_response.data
    if not isinstance(content, str): # Should be text
        raise RuntimeError(f"Unexpected content type for packages list: {type(content)}")


    blocks = content.strip().split("\n\n")
    latest_ver = None
    latest_block = None

    for block in blocks:
        if not block.startswith("Package: tailscale"):
            continue

        match = re.search(r"Version: (.+)", block)
        if not match:
            continue

        raw_version = match.group(1)
        version = normalize(raw_version)
        if not version:
            continue

        if not latest_ver or version > latest_ver:
            latest_ver = version
            latest_block = block

    if not latest_block:
        raise RuntimeError("tailscale package not found")

    filename_match = re.search(r"Filename: (.+)", latest_block)
    if not filename_match:
        raise RuntimeError("Filename not found in package block")
    
    filename_path = filename_match.group(1)
    download_url = BASE_DOWNLOAD_URL + filename_path
    
    local_name = filename_path.split("/")[-1]
    local_file_path = os.path.join(STATIC_DIR, local_name)

    print(f"Latest version: {latest_ver}")
    print(f"Package URL: {download_url}")
    print(f"Local file path: {local_file_path}")

    if os.path.exists(local_file_path):
        print(f"File {local_name} already exists in {STATIC_DIR}. Skipping download.")
        return local_name

    print(f"Downloading: {download_url}")
    deb_response: WebResponse = await http_session_manager.get_web_request("GET", download_url, return_type="bytes")
    
    if deb_response.status != 200:
        raise RuntimeError(f"Failed to download package: {deb_response.status} {deb_response.data}")

    deb_data = deb_response.data
    if not isinstance(deb_data, bytes): # Should be bytes
        raise RuntimeError(f"Unexpected content type for deb file: {type(deb_data)}")

    with open(local_file_path, "wb") as f:
        f.write(deb_data)

    print(f"Saved as: {local_file_path}")
    return local_name

async def main():
    try:
        file_name = await get_latest_version_package()
        print(f"Latest package file name: {file_name}")
    finally:
        await http_session_manager.close()

if __name__ == "__main__":
    asyncio.run(main())
