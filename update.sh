#!/bin/bash
dpkg-scanpackages -m debs > Packages
rm -f Packages.bz2 Packages.gz
bzip2 -9k Packages
gzip -9c Packages > Packages.gz
python3 make_release.py
