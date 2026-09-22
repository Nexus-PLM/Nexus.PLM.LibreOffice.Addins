"""The LibreOffice side: the document in front of the user, and how to get at it through UNO.

Everything here needs a running LibreOffice. Nothing else in the add-in does, which is why the
UNO-facing code is gathered in one file: the client and the command logic can be exercised without
an office at all.
"""

import os
import urllib.parse

# The five document services that can hold a PLM document, and the extension each is saved as.
# Math has no fields to drive beyond its metadata, but it is a document like any other and gets the
# same commands.
SERVICE_EXTENSIONS = (
    ("com.sun.star.text.TextDocument", ".odt"),
    ("com.sun.star.sheet.SpreadsheetDocument", ".ods"),
    ("com.sun.star.presentation.PresentationDocument", ".odp"),
    ("com.sun.star.drawing.DrawingDocument", ".odg"),
    ("com.sun.star.formula.FormulaProperties", ".odf"),
)

#: What this host can open, for the service's browser to filter by. A host declares its own
#: capabilities and they travel with the request.
OPENABLE_EXTENSIONS = ".odt;.ott;.ods;.ots;.odp;.otp;.odg;.otg;.odf;.otf"


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
    """The inverse, for handing a staged file back to the office to open."""
    return "file:///" + urllib.parse.quote(os.path.abspath(path).replace("\\", "/"))


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
    """The document window's handle, so a service dialog can be parented to it.

    Zero is a valid answer and means "no parent" — a dialog that is not parented is still shown,
    just not owned, which is better than refusing the command.
    """
    try:
        return int(document.getCurrentController().getFrame().getContainerWindow().getWindowHandle(()))
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
