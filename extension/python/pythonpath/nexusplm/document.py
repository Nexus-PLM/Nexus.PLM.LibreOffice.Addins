"""The LibreOffice side: the document in front of the user, and how to get at it through UNO.

Everything here needs a running LibreOffice. Nothing else in the add-in does, which is why the
UNO-facing code is gathered in one file: the client and the command logic can be exercised without
an office at all.
"""

import os
import urllib.parse

#: What this host can open, for the service's browser to filter by. A host declares its own
#: capabilities and they travel with the request; the service keeps no list of hosts.
OPENABLE_EXTENSIONS = ".odt;.ott;.ods;.ots;.odp;.otp;.odg;.otg;.odf;.otf"

#: The add-in's version, reported to About. Kept here rather than read from description.xml so
#: there is nothing to locate on disk at import time.
ADDIN_VERSION = "0.1.0"

# com.sun.star.lang.SystemDependent.SYSTEM_WIN32; the window-handle call wants to be told which
# windowing system's handle is being asked for.
_SYSTEM_WIN32 = 1


def desktop(context):
    """The office's desktop, through which documents are opened."""
    return context.ServiceManager.createInstanceWithContext(
        "com.sun.star.frame.Desktop", context)


def current(context):
    """The document the user is looking at, or ``None`` when there is none."""
    return desktop(context).getCurrentComponent()


def path_of(document):
    """The document's own file path, or ``None`` when it has never been saved.

    UNO gives a ``file:///`` URL; the service deals in paths, so it is converted here rather than
    at every call site.
    """
    url = getattr(document, "URL", None)
    if not url:
        return None
    return url_to_path(url)


def url_to_path(url):
    """``file:///C:/Nexus/Staging/EM-1.odt`` to ``C:\\Nexus\\Staging\\EM-1.odt``."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "file":
        return None

    path = urllib.parse.unquote(parsed.path)
    # A Windows path arrives as "/C:/..."; drop the leading slash and use native separators.
    if len(path) > 2 and path[0] == "/" and path[2] == ":":
        path = path[1:]
    return os.path.normpath(path)


def path_to_url(path):
    """The inverse, for handing a staged file back to the office to open.

    The drive colon and the separators stay as they are. Percent-encoding the colon produces a URL
    every zip tool and every browser accepts and LibreOffice does not: ``loadComponentFromURL`` on
    ``file:///C%3A/Nexus/Staging/LTD-00000001-ODT.ott`` raises ``IllegalArgumentException`` —
    "type detection failed" — because it never gets as far as looking at the file. Measured against
    LibreOffice 26.2: the same file at ``file:///C:/...`` opens.
    """
    return "file:///" + urllib.parse.quote(
        os.path.abspath(path).replace("\\", "/"), safe=":/")


def is_modified(document):
    """Whether the document has unsaved edits."""
    try:
        return bool(document.isModified())
    except Exception:
        # A document that cannot be asked counts as saved: the alternative is warning a user about
        # losing changes that may not exist.
        return False


def save(document):
    """Saves in place. Whether it worked is the caller's to check."""
    try:
        document.store()
        return True
    except Exception:
        return False


def close_without_saving(document):
    """Closes the document, discarding unsaved edits. Only after the user has said they may go."""
    try:
        document.setModified(False)
        document.close(True)
    except Exception:
        pass


def open_staged(context, path):
    """Opens a file the service staged, or brings it forward if it is already open.

    Opening a second copy of a file the user already has open is how "the document is already open"
    turns into two windows fighting over one path — and the add-in keys what it knows about a
    document on that path.
    """
    url = path_to_url(path)

    components = desktop(context).getComponents().createEnumeration()
    while components.hasMoreElements():
        component = components.nextElement()
        if getattr(component, "URL", None) == url:
            try:
                component.getCurrentController().getFrame().getContainerWindow().toFront()
            except Exception:
                pass
            return component

    return desktop(context).loadComponentFromURL(url, "_blank", 0, ())


def window_handle(document):
    """The document window's Win32 handle, so a service dialog can be parented to it.

    Asked for with the windowing system named, which is what the UNO call wants; asked with an
    empty argument it answers nothing useful. Zero is a valid answer and means "no parent" — a
    dialog that is not parented is still shown, just not owned, which is better than refusing the
    command. Unowned is exactly what the first version of this produced: the Open browser appeared
    behind a maximised Writer window, and looked like nothing had happened.
    """
    try:
        window = document.getCurrentController().getFrame().getContainerWindow()
        handle = window.getWindowHandle(b"", _SYSTEM_WIN32)
        return int(handle) if handle else 0
    except Exception:
        return 0


def user_fields(document):
    """The document's user-defined properties, name to text.

    These are the same ``meta:user-defined`` entries the ODF connector reads from a closed file, so
    a value lands identically whether the document is open or not.
    """
    values = {}
    try:
        container = document.getDocumentProperties().getUserDefinedProperties()
        for prop in container.getPropertySetInfo().getProperties():
            value = container.getPropertyValue(prop.Name)
            values[prop.Name] = "" if value is None else str(value)
    except Exception:
        pass
    return values


def write_user_fields(document, values):
    """Writes PLM's values into the user-defined properties the document already has.

    Only fields the document already carries are written — a field nobody put in the template is
    not a field of it. Returns how many were written. The document is marked modified so the
    change is saved with it.
    """
    if not values:
        return 0

    written = 0
    try:
        container = document.getDocumentProperties().getUserDefinedProperties()
        existing = {p.Name for p in container.getPropertySetInfo().getProperties()}
        wanted = {k.lower(): v for k, v in values.items()}

        for name in existing:
            value = wanted.get(name.lower())
            if value is None:
                continue
            try:
                container.setPropertyValue(name, "" if value is None else str(value))
                written += 1
            except Exception:
                # A typed property (date, number) refuses text it cannot hold. Leaving it alone is
                # the same decision the closed-file connector makes.
                pass

        if written:
            document.setModified(True)
    except Exception:
        pass
    return written
