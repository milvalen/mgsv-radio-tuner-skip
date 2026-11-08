"""Builds the release zip for Windows: the app, the bat files and an official Python runtime.

Run: python3 build_release.py
Downloads the Windows embeddable Python once into dist/cache and checks its SHA-256.
"""

import hashlib
import json
import os
import shutil
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))
sys.dont_write_bytecode = True

import luapatch  # noqa: E402

PYTHON_VERSION = "3.12.8"
PYTHON_ZIP = "python-%s-embed-amd64.zip" % PYTHON_VERSION
PYTHON_URL = "https://www.python.org/ftp/python/%s/%s" % (PYTHON_VERSION, PYTHON_ZIP)
PYTHON_SHA256 = "8d3f33be9eb810f23c102f08475af2854e50484b8e4e06275e937be61ce3d2fb"
APP_FILES = ("radio_tuner.py", "tuner.py", "qar.py", "luapatch.py")
PACKAGING_BATS = ("Install.bat", "Uninstall.bat")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def python_runtime(dist):
    cache = os.path.join(dist, "cache")
    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, PYTHON_ZIP)
    if not os.path.exists(path):
        print("Downloading", PYTHON_URL)
        urllib.request.urlretrieve(PYTHON_URL, path)
    got = sha256(path)
    if got != PYTHON_SHA256:
        os.remove(path)
        raise SystemExit("Wrong SHA-256 for %s: %s" % (PYTHON_ZIP, got))
    return path


def write_crlf(src, dst):
    """Windows cmd misreads bat files without CRLF line endings."""
    with open(src, encoding="ascii", newline=None) as f:
        text = f.read()
    with open(dst, "w", encoding="ascii", newline="\r\n") as f:
        f.write(text)


def main():
    with open(os.path.join(HERE, "VERSION"), encoding="ascii") as f:
        version = f.read().strip()
    dist = os.path.join(HERE, "dist")
    name = "MGSV-Radio-Tuner-Skip-%s" % version
    pkg = os.path.join(dist, name)
    runtime_zip = python_runtime(dist)
    shutil.rmtree(pkg, ignore_errors=True)
    os.makedirs(os.path.join(pkg, "app"))
    for fn in APP_FILES:
        shutil.copy(os.path.join(HERE, "src", fn), os.path.join(pkg, "app", fn))
    for fn in PACKAGING_BATS + ("README.txt",):
        write_crlf(os.path.join(HERE, "packaging", fn), os.path.join(pkg, fn))
    shutil.copy(os.path.join(HERE, "LICENSE"), os.path.join(pkg, "LICENSE.txt"))
    shutil.copy(os.path.join(HERE, "THIRD_PARTY_NOTICES.md"), os.path.join(pkg, "THIRD_PARTY_NOTICES.txt"))
    with open(os.path.join(pkg, "radio_tuner.json"), "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(luapatch.DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
    with zipfile.ZipFile(runtime_zip) as z:
        z.extractall(os.path.join(pkg, "runtime"))
    pth = os.path.join(pkg, "runtime", "python312._pth")
    with open(pth, "w", encoding="ascii", newline="\r\n") as f:
        f.write("..\\app\npython312.zip\n.\n")
    out = os.path.join(dist, name + ".zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _, files in sorted(os.walk(pkg)):
            for fn in sorted(files):
                full = os.path.join(root, fn)
                z.write(full, os.path.relpath(full, dist))
    print(out)
    print("%.1f MB" % (os.path.getsize(out) / 1e6))
    print("SHA-256", sha256(out))


if __name__ == "__main__":
    main()
