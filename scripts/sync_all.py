#!/usr/bin/env python3
"""
Unified sync engine for upstream packages from GitHub Releases and Cydia/APT repositories.
Configured via scripts/upstreams.json
"""
import os
import sys
import json
import glob
import bz2
import gzip
import hashlib
import urllib.request
import subprocess

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEBS_DIR = os.path.join(REPO_ROOT, "debs")
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "upstreams.json")

def get_file_sha256(filepath):
    if not os.path.isfile(filepath):
        return None
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest().lower()

def sync_github_release(entry):
    repo = entry["repo"]
    asset_name = entry["asset"]
    pkg_id = entry.get("id", repo)
    local_path = os.path.join(DEBS_DIR, asset_name)
    
    print(f"\n[GitHub] Checking {repo} for {asset_name}...")
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {"User-Agent": "cydia-repo-sync", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    req = urllib.request.Request(api_url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        release = json.loads(resp.read().decode("utf-8"))
        
    tag_name = release.get("tag_name", "")
    target_asset = None
    sha_asset = None
    for a in release.get("assets", []):
        if a.get("name") == asset_name:
            target_asset = a
        elif a.get("name") == "SHA256SUMS":
            sha_asset = a
            
    if not target_asset:
        print(f"[GitHub] Asset {asset_name} not found in release {tag_name}!")
        return False, None
        
    expected_sha256 = None
    if sha_asset:
        req_sha = urllib.request.Request(sha_asset["browser_download_url"], headers={"User-Agent": "cydia-repo-sync"})
        with urllib.request.urlopen(req_sha, timeout=30) as resp:
            for line in resp.read().decode("utf-8", errors="ignore").splitlines():
                if asset_name in line:
                    expected_sha256 = line.strip().split()[0].lower()
                    break
                    
    local_sha256 = get_file_sha256(local_path)
    if expected_sha256 and local_sha256 == expected_sha256:
        print(f"[GitHub] {pkg_id} is up to date ({tag_name}, SHA256 match).")
        return False, None
        
    print(f"[GitHub] Downloading {target_asset['browser_download_url']}...")
    req_deb = urllib.request.Request(target_asset["browser_download_url"], headers={"User-Agent": "cydia-repo-sync"})
    with urllib.request.urlopen(req_deb, timeout=120) as resp:
        deb_bytes = resp.read()
        
    downloaded_sha256 = hashlib.sha256(deb_bytes).hexdigest().lower()
    if expected_sha256 and downloaded_sha256 != expected_sha256:
        raise ValueError(f"Checksum mismatch for {asset_name}! Expected {expected_sha256}, got {downloaded_sha256}")
        
    with open(local_path, "wb") as f:
        f.write(deb_bytes)
        
    ver_cmd = subprocess.run(["dpkg-deb", "-f", local_path, "Version"], capture_output=True, text=True, check=True)
    version = ver_cmd.stdout.strip()
    print(f"[GitHub] Updated {pkg_id} -> {version} ({tag_name})")
    return True, f"{pkg_id} {version}"

def sync_cydia_repo(entry):
    packages_url = entry["packages_url"]
    pkg_name = entry["package"]
    target_arch = entry.get("arch", "iphoneos-arm")
    pkg_id = entry.get("id", pkg_name)
    
    print(f"\n[Cydia] Checking {packages_url} for {pkg_name} ({target_arch})...")
    req = urllib.request.Request(packages_url, headers={"User-Agent": "Telesphoreo APT-HTTP/1.0.592"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw_data = resp.read()
        
    if packages_url.endswith(".bz2"):
        text = bz2.decompress(raw_data).decode("utf-8", errors="ignore")
    elif packages_url.endswith(".gz"):
        text = gzip.decompress(raw_data).decode("utf-8", errors="ignore")
    else:
        text = raw_data.decode("utf-8", errors="ignore")
        
    upstream_pkg = None
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        fields = {}
        for line in block.splitlines():
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                fields[k.strip()] = v.strip()
        if fields.get("Package") == pkg_name and fields.get("Architecture") == target_arch:
            upstream_pkg = fields
            break
            
    if not upstream_pkg:
        print(f"[Cydia] Package {pkg_name} ({target_arch}) not found in upstream!")
        return False, None
        
    upstream_ver = upstream_pkg.get("Version")
    upstream_filename = upstream_pkg.get("Filename")
    upstream_deb_name = os.path.basename(upstream_filename)
    dest_path = os.path.join(DEBS_DIR, upstream_deb_name)
    
    # Check local files matching package
    local_pattern = os.path.join(DEBS_DIR, f"{pkg_name}_*_{target_arch}.deb")
    local_files = glob.glob(local_pattern)
    already_installed = False
    old_files_to_remove = []
    
    for f in local_files:
        if os.path.basename(f) == upstream_deb_name:
            already_installed = True
        else:
            old_files_to_remove.append(f)
            
    if already_installed and not old_files_to_remove:
        print(f"[Cydia] {pkg_id} is up to date ({upstream_deb_name}).")
        return False, None
        
    # Determine deb URL
    base_repo_url = packages_url.rsplit("/", 1)[0]
    if base_repo_url.endswith("/Packages") or base_repo_url.endswith("/Packages.bz2") or base_repo_url.endswith("/Packages.gz"):
        base_repo_url = base_repo_url.rsplit("/", 1)[0]
    upstream_deb_url = f"{base_repo_url}/{upstream_filename}"
    
    print(f"[Cydia] Downloading {upstream_deb_url}...")
    req_deb = urllib.request.Request(upstream_deb_url, headers={"User-Agent": "Telesphoreo APT-HTTP/1.0.592"})
    with urllib.request.urlopen(req_deb, timeout=60) as resp:
        deb_bytes = resp.read()
        
    with open(dest_path, "wb") as f:
        f.write(deb_bytes)
        
    for old_f in old_files_to_remove:
        print(f"[Cydia] Removing old file {old_f}")
        os.remove(old_f)
        
    print(f"[Cydia] Updated {pkg_id} -> {upstream_ver}")
    return True, f"{pkg_id} {upstream_ver}"

def main():
    if not os.path.isfile(CONFIG_PATH):
        print(f"Config {CONFIG_PATH} not found!")
        sys.exit(1)
        
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        upstreams = json.load(f)
        
    updated_items = []
    for entry in upstreams:
        src_type = entry.get("type")
        try:
            if src_type == "github_release":
                updated, summary = sync_github_release(entry)
            elif src_type == "cydia_repo":
                updated, summary = sync_cydia_repo(entry)
            else:
                print(f"Unknown source type: {src_type}")
                continue
                
            if updated and summary:
                updated_items.append(summary)
        except Exception as e:
            print(f"Error syncing {entry.get('id', 'unknown')}: {e}")
            
    if updated_items:
        print(f"\nPackages updated: {', '.join(updated_items)}")
        update_sh = os.path.join(REPO_ROOT, "update.sh")
        print(f"Regenerating repo metadata via {update_sh}...")
        subprocess.run(["bash", update_sh], cwd=REPO_ROOT, check=True)
        
        summary_str = ", ".join(updated_items)
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as gh_out:
                gh_out.write("updated=true\n")
                gh_out.write(f"summary={summary_str}\n")
    else:
        print("\nAll upstream packages are up to date. No changes.")
        if "GITHUB_OUTPUT" in os.environ:
            with open(os.environ["GITHUB_OUTPUT"], "a") as gh_out:
                gh_out.write("updated=false\n")
                
    return 0

if __name__ == "__main__":
    sys.exit(main())
