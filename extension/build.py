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


def check_manifest():
    """Every configuration file in the folder is named by the manifest, and every named file exists.

    A .xcu that the manifest does not list is simply not read. The extension installs, reports
    success, and the thing it configures never appears — no error anywhere. That is how the whole
    manifest came to live in META-INF/ in the first place, and a forgotten entry for a new file is
    the same failure wearing a different hat.
    """
    manifest = open(os.path.join(HERE, "META-INF", "manifest.xml"), encoding="utf-8").read()
    listed = set(re.findall(r'manifest:full-path="([^"]+)"', manifest))

    missing_from_disk = sorted(
        path for path in listed
        if not path.endswith("/") and not os.path.exists(os.path.join(HERE, path)))
    if missing_from_disk:
        raise SystemExit("the manifest names files that do not exist: "
                         + ", ".join(missing_from_disk))

    on_disk = {name for name in os.listdir(HERE) if name.endswith(".xcu")}
    unlisted = sorted(on_disk - listed)
    if unlisted:
        raise SystemExit("configuration files the manifest does not name, so LibreOffice will "
                         "never read them: " + ", ".join(unlisted))
    print("  manifest: names every .xcu, and every file it names exists")


def check_sidebar():
    """The sidebar's three halves agree with each other.

    A panel names a factory by a URL; a factory is registered under a name; and the component
    behind it declares an implementation name. If any two of those disagree the deck still appears
    in the rail and opens **empty**, because as far as LibreOffice is concerned nobody claimed the
    resource — and nothing is logged. Each of these is one typo away at all times.
    """
    sidebar = open(os.path.join(HERE, "Sidebar.xcu"), encoding="utf-8").read()
    factories = open(os.path.join(HERE, "Factories.xcu"), encoding="utf-8").read()
    component = open(os.path.join(HERE, "python", "nexusplm_sidebar.py"), encoding="utf-8").read()

    # Only what is inside a <value>, so the URL written out in this file's own explanatory comment
    # is not mistaken for a declaration — it matched, and the complaint came back wearing the
    # comment as a panel name.
    urls = re.findall(r"<value>private:resource/toolpanel/([^/<]+)/([^<]+)</value>", sidebar)
    if not urls:
        raise SystemExit("Sidebar.xcu declares no panel ImplementationURL")

    registered = dict(zip(
        re.findall(r'oor:name="Name" oor:type="xs:string"><value>([^<]+)</value>', factories),
        re.findall(r'<value>([\w.]+)</value>\s*</prop>\s*</node>', factories)))

    for factory_name, panel_id in urls:
        if factory_name not in registered:
            raise SystemExit(
                "panel '%s' names the factory '%s', which Factories.xcu does not register — the "
                "deck would open empty" % (panel_id.strip(), factory_name))

        implementation = registered[factory_name]
        if ('"%s"' % implementation) not in component:
            raise SystemExit(
                "Factories.xcu points '%s' at the implementation '%s', which "
                "python/nexusplm_sidebar.py does not declare" % (factory_name, implementation))

    # A ContextList descriptor is itself "application, context, state" — comma separated — so a
    # comma as the LIST separator tears every descriptor into fragments, nothing ever matches the
    # document's context, and the deck never appears in the rail. Nothing is logged; the extension
    # installs and reports success. Measured on 26.2, which is how this check came to exist.
    for separator in re.findall(r'<value oor:separator="([^"]+)">', sidebar):
        if separator == ",":
            raise SystemExit(
                'a ContextList is written with oor:separator="," — each descriptor is already '
                'comma separated, so the deck would never appear. Use ";"')

    # A deck nobody's panel belongs to, or a panel belonging to no deck, is the same silent miss.
    decks = set(re.findall(r'oor:name="Id" oor:type="xs:string"><value>(\w*Deck)</value>', sidebar))
    for deck_id in re.findall(r'oor:name="DeckId" oor:type="xs:string"><value>([^<]+)</value>', sidebar):
        if deck_id not in decks:
            raise SystemExit("a panel belongs to the deck '%s', which Sidebar.xcu does not define"
                             % deck_id)

    print("  sidebar: panel, factory and component agree (%s)" % ", ".join(sorted(decks)))


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
    check_manifest()
    check_sidebar()
    package = pack()
    sys.exit(install(package) if "--install" in sys.argv else 0)
