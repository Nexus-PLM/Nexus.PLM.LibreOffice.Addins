"""The OpenDocument package itself, for the one thing the add-in has to do to a closed file.

Everything else about a document is done through UNO, with the office open. This is not: a file
staged from a type's template carries the template's body, and an office asked to open a template
opens a *copy* of it — a new "Untitled 1" — and never touches the file again. By the time the
document is open it is too late to notice.

The .NET connector (``OdfPackage``) holds the same rule for the server side. This is the same rule
for the client side, in the only place the client can apply it.
"""

import os
import re
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

#: Where a package keeps its user-defined properties.
META = "meta.xml"

#: Where a package says what each of its parts is — including, in its root entry, what the
#: package itself is. ODF requires that to agree with ``mimetype``.
MANIFEST = "META-INF/manifest.xml"

#: The extensions a document of each of those types is named with.
DOCUMENT_EXTENSIONS = {".odt", ".ods", ".odp", ".odg", ".odf"}


def mime_type_of(path):
    """What the package says it is, or ``None`` when it is not an OpenDocument package at all."""
    try:
        with zipfile.ZipFile(path) as package:
            return package.read("mimetype").decode("ascii").strip()
    except Exception:
        return None


def make_document(path, values=None):
    """Makes the staged file the document PLM means it to be. Returns whether it changed.

    Two things, both before the office is asked to open it and both for the same reason — that
    afterwards is too late:

    * a template body is made into the document it stands for. A file staged from a type's
      template still says it is a template, whatever it is named, and an office opens a template by
      making an untitled copy and leaving the file alone.
    * PLM's values are written in. They used to be written into the open document instead, which
      works only for as long as nothing asks the file itself what it holds — and Check In, a
      backup, a colleague opening the staged path, all do.

    A file that needs neither is not rewritten at all.
    """
    values = values or {}
    mime_type = mime_type_of(path)
    if mime_type is None:
        return False

    # A template body under a document's name is the mismatch to correct. A file genuinely named
    # as a template is left as one: opening a real template means to use it as one.
    document_type = None
    if os.path.splitext(path)[1].lower() in DOCUMENT_EXTENSIONS:
        document_type = DOCUMENT_MIME_TYPES.get(mime_type)

    if document_type is None and not values:
        return False

    folder = os.path.dirname(os.path.abspath(path))
    handle, temporary = tempfile.mkstemp(dir=folder, suffix=".tmp")
    os.close(handle)
    try:
        with zipfile.ZipFile(path) as source, zipfile.ZipFile(temporary, "w") as target:
            # mimetype first and uncompressed, as ODF requires of every package.
            target.writestr(_stored("mimetype"), document_type or mime_type)
            for entry in source.infolist():
                if entry.filename == "mimetype":
                    continue

                content = source.read(entry.filename)
                if entry.filename == MANIFEST and document_type is not None:
                    content = _manifest_says(content, mime_type, document_type)
                elif entry.filename == META and values:
                    content = _meta_holds(content, values)

                target.writestr(entry, content)
        shutil.move(temporary, path)
        return True
    except Exception:
        try:
            os.unlink(temporary)
        except Exception:
            pass
        # The file is untouched, so the office still opens something — what it opened before this
        # was written — rather than nothing at all.
        return False


def _meta_holds(meta, values):
    """PLM's values, written into the user-defined properties the document already has.

    Only fields the document carries are written — a field nobody put in the template is not a
    field of it — and each keeps the type it was given, which is the rule ``OdfValueWrite`` keeps
    for the server and ``document.typed_value`` keeps for an open document. A value that is not a
    value of that type leaves the property alone.
    """
    text = meta.decode("utf-8")
    wanted = {name.lower(): value for name, value in values.items()}

    def replace(match):
        whole, name, kind, current = match.group(0), match.group(1), match.group(2), match.group(3)
        incoming = wanted.get(name.lower())
        if incoming is None:
            return whole

        lexical = _lexical(kind, incoming)
        if lexical is None:
            return whole

        head = whole[:whole.index(">") + 1]
        return head + _escaped(lexical) + "</meta:user-defined>"

    return _FIELD.sub(replace, text).encode("utf-8")


#: One ``meta:user-defined`` element: its name, its declared type, and what it holds.
_FIELD = re.compile(
    r'<meta:user-defined meta:name="([^"]+)"'
    r'(?:[^>]*?meta:value-type="([^"]+)")?[^>]*>([^<]*)</meta:user-defined>')


def _lexical(kind, text):
    """``text`` as the type demands it, or ``None`` when it is not a value of that type."""
    text = "" if text is None else str(text).strip()
    kind = (kind or "string").lower()

    if kind == "string":
        return text
    if not text:
        # An empty value is not a date, a number or a flag, and blanking a typed field would lose
        # the template author's value.
        return None

    if kind == "boolean":
        lowered = text.lower()
        if lowered in ("true", "yes", "y", "1"):
            return "true"
        if lowered in ("false", "no", "n", "0"):
            return "false"
        return None

    if kind == "float":
        try:
            number = float(text)
        except ValueError:
            return None
        return repr(int(number)) if number.is_integer() else repr(number)

    if kind == "date":
        head = text.replace("/", "-").split("T")[0].split(" ")[0]
        parts = head.split("-")
        if len(parts) != 3:
            return None
        try:
            year, month, day = (int(part) for part in parts)
        except ValueError:
            return None
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        return "%04d-%02d-%02dT00:00:00" % (year, month, day)

    return text


def _escaped(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _manifest_says(manifest, was, now):
    """The manifest's root entry, changed from the template's type to the document's.

    A package whose ``mimetype`` and whose manifest disagree about what it is opens with
    "(repaired document)" across the title bar and a dialog behind it: LibreOffice believes the
    file damaged, because by ODF the two have to say the same thing. Only the root entry is
    touched — every other entry names a part, not the document.
    """
    root = b'manifest:full-path="/"'
    if root not in manifest:
        return manifest

    start = manifest.index(root)
    end = manifest.index(b">", start)
    entry = manifest[start:end]
    return manifest[:start] + entry.replace(was.encode("ascii"), now.encode("ascii")) + manifest[end:]


def _stored(name):
    info = zipfile.ZipInfo(name)
    info.compress_type = zipfile.ZIP_STORED
    return info
