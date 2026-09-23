"""The OpenDocument package itself, for the one thing the add-in has to do to a closed file.

Everything else about a document is done through UNO, with the office open. This is not: a file
staged from a type's template carries the template's body, and an office asked to open a template
opens a *copy* of it — a new "Untitled 1" — and never touches the file again. By the time the
document is open it is too late to notice.

The .NET connector (``OdfPackage``) holds the same rule for the server side. This is the same rule
for the client side, in the only place the client can apply it.
"""

import os
import shutil
import tempfile
import zipfile

#: What a template's body says, and what the document made from it says instead. Writer, Calc,
#: Impress, Draw and Math, each with its template type.
DOCUMENT_MIME_TYPES = {
    "application/vnd.oasis.opendocument.text-template":
        "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet-template":
        "application/vnd.oasis.opendocument.spreadsheet",
    "application/vnd.oasis.opendocument.presentation-template":
        "application/vnd.oasis.opendocument.presentation",
    "application/vnd.oasis.opendocument.graphics-template":
        "application/vnd.oasis.opendocument.graphics",
    "application/vnd.oasis.opendocument.formula-template":
        "application/vnd.oasis.opendocument.formula",
}

#: The extensions a document of each of those types is named with.
DOCUMENT_EXTENSIONS = {".odt", ".ods", ".odp", ".odg", ".odf"}


def mime_type_of(path):
    """What the package says it is, or ``None`` when it is not an OpenDocument package at all."""
    try:
        with zipfile.ZipFile(path) as package:
            return package.read("mimetype").decode("ascii").strip()
    except Exception:
        return None


def make_document(path):
    """Turns a staged template body into the document it is named as. Returns whether it changed.

    Called on the file PLM staged, before the office is asked to open it. A file that is already a
    document, is not an OpenDocument package, or is named as a template is left exactly as it is:
    this is about the one mismatch — a document's name over a template's body — and nothing else.
    """
    extension = os.path.splitext(path)[1].lower()
    if extension not in DOCUMENT_EXTENSIONS:
        return False

    mime_type = mime_type_of(path)
    document_type = DOCUMENT_MIME_TYPES.get(mime_type)
    if document_type is None:
        return False

    folder = os.path.dirname(os.path.abspath(path))
    handle, temporary = tempfile.mkstemp(dir=folder, suffix=".tmp")
    os.close(handle)
    try:
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(temporary, "w") as target:
            # mimetype first and uncompressed, as ODF requires of every package.
            target.writestr(_stored("mimetype"), document_type)
            for entry in source.infolist():
                if entry.filename == "mimetype":
                    continue
                target.writestr(entry, source.read(entry.filename))
        shutil.move(temporary, path)
        return True
    except Exception:
        try:
            os.unlink(temporary)
        except Exception:
            pass
        # The file is untouched, so the office still opens something — a template copy, which is
        # the old behaviour, rather than nothing at all.
        return False


def _stored(name):
    info = zipfile.ZipInfo(name)
    info.compress_type = zipfile.ZIP_STORED
    return info
