#!/usr/bin/env python3
"""
Sync vless-core package from upstream repository https://github.com/notfence/vless-core-app
"""
import os
import sys
import json
import hashlib
import urllib.request
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEBS_DIR = os.path.join(REPO_ROOT, "debs")
LOCAL_DEB = os.path.join(DEBS_DIR, "com.vlesscore.app_iphoneos-arm.deb")
GITHUB_API_URL = "https://api.github.com/repos/notfence/vless-core-app/releases/latest"

def get_file_sha256(filepath):
    if not os.path.isfile(filepath):
        return None
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def get_latest_release():
    headers = {
        "User-Agent": "cydia-repo-sync",
        "Accept": "application/vnd.github+json"
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    req = urllib.request.Request(GITHUB_API_URL, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    print("Checking upstream notfence/vless-core-app for latest release...")
    release = get_latest_release()
    tag_name = release.get("tag_name", "")
    print(f"Latest upstream release: {tag_name}")
    
    deb_asset = None
    sha_asset = None
    for asset in release.get("assets", []):
        name = asset.get("name", "")
        if name == "com.vlesscore.app_iphoneos-arm.deb":
            deb_asset = asset
        elif name == "SHA256SUMS":
            sha_asset = asset
            
    if not deb_asset:
        raise RuntimeError("com.vlesscore.app_iphoneos-arm.deb not found in release assets")
        
    expected_sha256 = None
    if sha_asset:
        req = urllib.request.Request(sha_asset["browser_download_url"], headers={"User-Agent": "cydia-repo-sync"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            sums_text = resp.read().decode("utf-8", errors="ignore")
            for line in sums_text.splitlines():
                if "com.vlesscore.app_iphoneos-arm.deb" in line:
                    expected_sha256 = line.strip().split()[0].lower()
                    break
                    
    local_sha256 = get_file_sha256(LOCAL_DEB)
    print(f"Local SHA256:    {local_sha256}")
    print(f"Expected SHA256: {expected_sha256}")
    
    if expected_sha256 and local_sha256 == expected_sha256:
        print(f"vless-core is already up to date ({tag_name}).")
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as gh_out:
                gh_out.write("updated=false\n")
        return 0
        
    print(f"New release detected! Downloading {deb_asset['browser_download_url']}...")
    req = urllib.request.Request(deb_asset["browser_download_url"], headers={"User-Agent": "cydia-repo-sync"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        deb_bytes = resp.read()
        
    downloaded_sha256 = hashlib.sha256(deb_bytes).hexdigest().lower()
    if expected_sha256 and downloaded_sha256 != expected_sha256:
        raise ValueError(f"Checksum mismatch! Expected {expected_sha256}, got {downloaded_sha256}")
        
    with open(LOCAL_DEB, "wb") as f:
        f.write(deb_bytes)
        
    # Read version from deb
    ver_cmd = subprocess.run(["dpkg-deb", "-f", LOCAL_DEB, "Version"], capture_output=True, text=True, check=True)
    deb_version = ver_cmd.stdout.strip()
    print(f"Successfully saved {LOCAL_DEB} (Version: {deb_version}, Size: {len(deb_bytes)} bytes)")
    
    # Run update.sh
    update_sh = os.path.join(REPO_ROOT, "update.sh")
    print(f"Running {update_sh}...")
    subprocess.run(["bash", update_sh], cwd=REPO_ROOT, check=True)
    
    print(f"Successfully updated vless-core to {deb_version} ({tag_name})!")
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as gh_out:
            gh_out.write("updated=true\n")
            gh_out.write(f"version={deb_version}\n")
            gh_out.write(f"tag={tag_name}\n")
            
    return 0

if __name__ == "__main__":
    sys.exit(main())
