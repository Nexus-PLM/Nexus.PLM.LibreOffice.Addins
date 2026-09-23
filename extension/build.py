"""Packs the extension folder into NexusPLM.oxt, and makes the icons it needs.

An .oxt is a zip. Nothing here needs LibreOffice, so it runs anywhere:

    python extension/build.py            # writes dist/NexusPLM.oxt
    python extension/build.py --install   # and installs it with unopkg
"""

import os
import shutil
import subprocess
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DIST = os.path.join(ROOT, "dist")
OXT = os.path.join(DIST, "NexusPLM.oxt")

SOFFICE_DIRS = (
    r"C:\Program Files\LibreOffice\program",
    r"C:\Program Files (x86)\LibreOffice\program",
    "/usr/lib/libreoffice/program",
)

# The icons are the Word add-in's own, resized: LibreOffice wants 16px and 26px per command
# (ImageIdentifier "%origin%/icons/<Name>" is a stem, and _16/_26 are appended by LibreOffice),
# and 42px for the extension manager card. They are checked in; this only complains if one that
# Addons.xcu names is missing, which is how a renamed icon would otherwise fail silently — the
# button appears with no image and no error.
import re


def check_icons():
    icons = os.path.join(HERE, "icons")
    xcu = open(os.path.join(HERE, "Addons.xcu"), encoding="utf-8").read()
    missing = []
    # Two forms name an icon: an ImageIdentifier stem ("icons/New", sizes appended by LibreOffice)
    # and an Images entry's explicit file ("icons/New_16.png"). Check whichever files each implies.
    wanted = set()
    for ref in set(re.findall(r"%origin%/icons/([\w.]+)", xcu)):
        if ref.endswith(".png"):
            wanted.add(ref)
        else:
            wanted.update("%s_%d.png" % (ref, size) for size in (16, 26))
    # Compared against the directory listing, not os.path.exists: Windows would answer yes for
    # Nexus_16.png when the file is nexus_16.png, and the Linux runner would then fail on the
    # very same commit. This check has to give the same answer on both.
    present = set(os.listdir(icons))
    for name in sorted(wanted):
        if name not in present:
            missing.append(name)
    if not os.path.exists(os.path.join(icons, "nexus-42.png")):
        missing.append("nexus-42.png")
    if missing:
        raise SystemExit("icons missing from extension/icons: " + ", ".join(missing))
    print("  icons: every one Addons.xcu names is present")


def pack():
    os.makedirs(DIST, exist_ok=True)
    if os.path.exists(OXT):
        os.remove(OXT)

    included = 0
    with zipfile.ZipFile(OXT, "w", zipfile.ZIP_DEFLATED) as oxt:
        for folder, _dirs, files in os.walk(HERE):
            for name in files:
                full = os.path.join(folder, name)
                relative = os.path.relpath(full, HERE).replace("\\", "/")

                # The build script itself and anything Python left behind are not the extension.
                if relative == "build.py" or "__pycache__" in relative:
                    continue

                oxt.write(full, relative)
                included += 1

    print("packed %s (%d files, %d bytes)" % (OXT, included, os.path.getsize(OXT)))
    return OXT


def unopkg():
    for folder in SOFFICE_DIRS:
        for name in ("unopkg.com", "unopkg"):
            candidate = os.path.join(folder, name)
            if os.path.exists(candidate):
                return candidate
    return None


def install(path):
    tool = unopkg()
    if tool is None:
        print("unopkg not found: install by hand with Tools > Extension Manager")
        return 1

    # LibreOffice must not be running, or unopkg cannot write the extension cache.
    for command in (["remove", "com.nexusplm.libreoffice"], ["add", "-f", path]):
        result = subprocess.run([tool] + command, capture_output=True, text=True)
        label = command[0]
        if result.returncode != 0 and label != "remove":
            print("unopkg %s failed:\n%s\n%s" % (label, result.stdout, result.stderr))
            return result.returncode
        print("unopkg %s: ok" % label)
    return 0


if __name__ == "__main__":
    check_icons()
    package = pack()
    sys.exit(install(package) if "--install" in sys.argv else 0)
