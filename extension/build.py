"""Packs the extension folder into NexusPLM.oxt, and makes the icons it needs.

An .oxt is a zip. Nothing here needs LibreOffice, so it runs anywhere:

    python extension/build.py            # writes dist/NexusPLM.oxt
    python extension/build.py --install   # and installs it with unopkg
"""

import os
import shutil
import struct
import subprocess
import sys
import zlib
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

# What LibreOffice asks an extension for. The toolbar uses 16px and 26px — not 32 and 64, which is
# the Office convention and produces a blurry button here. 42px is the extension manager's own.
ICON_SIZES = (16, 26, 42)

#: The Nexus accent, as the rest of the product uses it.
ACCENT = (0x1E, 0x9B, 0xD6)


def _png(path, size, rgb):
    """A square PNG of one colour, written without any imaging library.

    Placeholder art, deliberately: a real icon is a design asset, and inventing one badly is worse
    than a plain square that is obviously a placeholder.
    """
    red, green, blue = rgb
    # One filter byte (0 = none) then RGB triples, per scanline.
    row = b"\x00" + bytes((red, green, blue)) * size
    raw = row * size

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    header = struct.pack(">2I5B", size, size, 8, 2, 0, 0, 0)   # 8-bit, truecolour
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(chunk(b"IHDR", header))
        handle.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        handle.write(chunk(b"IEND", b""))


def make_icons():
    icons = os.path.join(HERE, "icons")
    os.makedirs(icons, exist_ok=True)
    for size in ICON_SIZES:
        target = os.path.join(icons, "nexus-%d.png" % size)
        if not os.path.exists(target):
            _png(target, size, ACCENT)
            print("  made icons/nexus-%d.png" % size)

    # Addons.xcu points at "%origin%/icons/nexus"; LibreOffice appends _16 and _26 itself.
    for size, suffix in ((16, "_16"), (26, "_26")):
        target = os.path.join(icons, "nexus%s.png" % suffix)
        if not os.path.exists(target):
            shutil.copyfile(os.path.join(icons, "nexus-%d.png" % size), target)
            print("  made icons/nexus%s.png" % suffix)


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
    make_icons()
    package = pack()
    sys.exit(install(package) if "--install" in sys.argv else 0)
