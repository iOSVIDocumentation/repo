import os
import hashlib
import email.utils
import datetime

repo_dir = os.path.dirname(os.path.abspath(__file__))

header = f"""Origin: iOS VI Documentation
Label: iOS VI Documentation
Suite: stable
Version: 1.0
Codename: ios
Architectures: iphoneos-arm
Components: main
Description: archive tweaks
Date: {email.utils.format_datetime(datetime.datetime.now(datetime.timezone.utc))}"""

files = ["Packages", "Packages.gz", "Packages.bz2"]
md5s, sha1s, sha256s = [], [], []

for f in files:
    filepath = os.path.join(repo_dir, f)
    data = open(filepath, "rb").read()
    size = len(data)
    md5 = hashlib.md5(data).hexdigest()
    sha1 = hashlib.sha1(data).hexdigest()
    sha256 = hashlib.sha256(data).hexdigest()
    md5s.append(f" {md5} {size:16d} {f}")
    sha1s.append(f" {sha1} {size:16d} {f}")
    sha256s.append(f" {sha256} {size:16d} {f}")

out = header + "\nMD5Sum:\n" + "\n".join(md5s) + "\nSHA1:\n" + "\n".join(sha1s) + "\nSHA256:\n" + "\n".join(sha256s) + "\n"

with open(os.path.join(repo_dir, "Release"), "w", encoding="utf-8") as rf:
    rf.write(out)

print("Updated Release successfully.")
