#!/usr/bin/env python3
"""
Sync Witch package from upstream repository https://repo.k0.tel/
"""
import os
import sys
import glob
import bz2
import urllib.request
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEBS_DIR = os.path.join(REPO_ROOT, "debs")
UPSTREAM_PACKAGES_URL = "https://repo.k0.tel/Packages.bz2"
PACKAGE_ID = "com.koutsie.witch"
TARGET_ARCH = "iphoneos-arm"

def get_upstream_witch_info():
    req = urllib.request.Request(
        UPSTREAM_PACKAGES_URL,
        headers={"User-Agent": "Telesphoreo APT-HTTP/1.0.592"}
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
    text = bz2.decompress(data).decode("utf-8", errors="ignore")
    
    candidates = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        fields = {}
        for line in block.splitlines():
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                fields[k.strip()] = v.strip()
        
        if fields.get("Package") == PACKAGE_ID:
            arch = fields.get("Architecture")
            ver = fields.get("Version")
            filename = fields.get("Filename")
            if arch == TARGET_ARCH and filename and ver:
                candidates.append((ver, filename, fields))
    
    if not candidates:
        raise RuntimeError("No matching Witch package found in upstream repository")
    
    return candidates[0]

def get_local_witch_files():
    pattern = os.path.join(DEBS_DIR, f"{PACKAGE_ID}_*_{TARGET_ARCH}.deb")
    return glob.glob(pattern)

def main():
    upstream_ver, upstream_filename, fields = get_upstream_witch_info()
    upstream_deb_url = f"https://repo.k0.tel/{upstream_filename}"
    upstream_deb_name = os.path.basename(upstream_filename)
    
    print(f"Upstream Witch ({TARGET_ARCH}): version {upstream_ver}, file: {upstream_deb_name}")
    
    local_files = get_local_witch_files()
    already_installed = False
    old_files_to_remove = []
    
    for f in local_files:
        fname = os.path.basename(f)
        if fname == upstream_deb_name:
            already_installed = True
        else:
            old_files_to_remove.append(f)
            
    if already_installed and not old_files_to_remove:
        print(f"Witch is already up to date ({upstream_deb_name}).")
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as gh_out:
                gh_out.write("updated=false\n")
        return 0
        
    print(f"Updating Witch to {upstream_ver}...")
    dest_path = os.path.join(DEBS_DIR, upstream_deb_name)
    
    req = urllib.request.Request(
        upstream_deb_url,
        headers={"User-Agent": "Telesphoreo APT-HTTP/1.0.592"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        deb_data = resp.read()
        
    with open(dest_path, "wb") as f:
        f.write(deb_data)
    print(f"Downloaded {dest_path} ({len(deb_data)} bytes)")
    
    for old_f in old_files_to_remove:
        print(f"Removing old version: {old_f}")
        os.remove(old_f)
        
    update_sh = os.path.join(REPO_ROOT, "update.sh")
    print(f"Running {update_sh}...")
    subprocess.run(["bash", update_sh], cwd=REPO_ROOT, check=True)
    
    print(f"Successfully updated Witch to {upstream_ver}!")
    if "GITHUB_OUTPUT" in os.environ:
        with open(os.environ["GITHUB_OUTPUT"], "a") as gh_out:
            gh_out.write("updated=true\n")
            gh_out.write(f"version={upstream_ver}\n")
            
    return 0

if __name__ == "__main__":
    sys.exit(main())
