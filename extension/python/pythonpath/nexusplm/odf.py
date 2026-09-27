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

#: Where a package keeps its body — and, in a presentation or a drawing, the named shapes that
#: are the only place a value can be SEEN. A user field is in File > Properties; a slide is not.
CONTENT = "content.xml"

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


class RewriteError(Exception):
    """The staged file could not be rewritten. It is untouched — the office still opens what it
    would have opened before — but what it opens is not what PLM meant it to be, and that used to
    happen in silence: the failure looked exactly like a template whose fields did not match."""


def make_document(path, values=None):
    """Makes the staged file the document PLM means it to be. Returns whether it changed.

    Two things, both before the office is asked to open it and both for the same reason — that
    afterwards is too late:

    * a template body is made into the document it stands for. A file staged from a type's
      template still says it is a template, whatever it is named, and an office opens a template by
      making an untitled copy and leaving the file alone.
    * PLM's values are written in. They used to be written into the open document instead, which
      works only for as long as nothing asks the file itself what it holds — and Check In, a
      backup, a colleague opening the staged path, all do. Into the user fields, which every
      application carries, and into the named frames and shapes of the body, which are the only
      place a value shows on a slide or a drawing page.

    A file that needs neither is not rewritten at all. A file that needed rewriting and could not
    be raises :class:`RewriteError`, with the file left as it was.
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
                elif entry.filename == CONTENT and values:
                    content = _content_holds(content, values)

                target.writestr(entry, content)
        shutil.move(temporary, path)
        return True
    except Exception as trouble:
        try:
            os.unlink(temporary)
        except Exception:
            pass
        # The file is untouched, so the office still opens something — what it opened before this
        # was written — rather than nothing at all. But it is not what PLM meant, so the caller is
        # told; returning False here made this indistinguishable from a file that needed nothing.
        raise RewriteError("%s: %s" % (os.path.basename(path), trouble))


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
        whole, attributes = match.group(0), match.group("attributes")

        name = _NAME.search(attributes)
        if name is None:
            return whole

        incoming = wanted.get(name.group(1).lower())
        if incoming is None:
            return whole

        kind = _KIND.search(attributes)
        lexical = _lexical(kind.group(1) if kind else None, incoming)
        if lexical is None:
            return whole

        return "<meta:user-defined%s>%s</meta:user-defined>" % (
            attributes.rstrip(), _escaped(lexical))

    return _FIELD.sub(replace, text).encode("utf-8")


#: One ``meta:user-defined`` element, in both the shapes a document holds it in: with a value, and
#: self-closing when it has none. The empty ones are exactly the fields PLM fills in, and a pattern
#: that only matched the first shape skipped every one of them — the part number above all.
_FIELD = re.compile(
    r'<meta:user-defined(?P<attributes>[^>]*?)'
    r'(?:/>|>[^<]*</meta:user-defined>)')

_NAME = re.compile(r'meta:name="([^"]+)"')
_KIND = re.compile(r'meta:value-type="([^"]+)"')


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


# ── named shapes ────────────────────────────────────────────────────────────
# The same rule the server's LibreOfficeTemplateConnector keeps: a frame or shape somebody named
# (``draw:name``) is a field; an unnamed one is not. Measured there against files LibreOffice 26.2
# wrote itself: an untouched placeholder carries no name attribute at all, so a name existing IS
# the signal, and no list of suspicious words is needed. The text goes into the first paragraph,
# inside its first span so the author's font, size and colour survive; whatever follows is the old
# value's remainder and goes.
#
# Text, not a parser: LibreOffice's content.xml declares thirty-odd namespaces on its root, and
# the standard library's ElementTree rewrites every prefix it was not told about, which is the
# quickest way to a file that opens as "(repaired document)". meta.xml is handled the same way,
# for the same reason.

#: The opening tag of a frame, custom shape or text box that carries a name. Not self-closing:
#: a shape with no body has no text to write.
_NAMED_SHAPE = re.compile(
    r'<draw:(?P<tag>frame|custom-shape|text-box)\b[^>]*?\bdraw:name="(?P<name>[^"]*)"[^>]*?(?<!/)>')

#: A text box's opening tag, inside a frame. Its name, when it has one of its own, is not looked
#: at here: the frame's is the one the server reads.
_TEXT_BOX = re.compile(r'<draw:text-box\b[^>]*?(?<!/)>')

#: One paragraph, in both the shapes it comes in. Paragraphs never nest, so non-greedy is exact.
_PARAGRAPH = re.compile(r'<text:p\b(?P<attributes>[^>]*?)(?:/>|>(?P<inner>.*?)</text:p>)', re.DOTALL)

#: One span, likewise.
_SPAN = re.compile(r'<text:span\b(?P<attributes>[^>]*?)(?:/>|>.*?</text:span>)', re.DOTALL)


def _content_holds(content, values):
    """PLM's values, written into the named frames and shapes the body already has."""
    text = content.decode("utf-8")
    wanted = {name.lower(): value for name, value in values.items()}

    out = []
    position = 0
    while True:
        match = _NAMED_SHAPE.search(text, position)
        if match is None:
            break

        end = _element_end(text, match.group("tag"), match.end())
        incoming = wanted.get(match.group("name").lower())
        if end < 0 or incoming is None:
            out.append(text[position:match.end()])
            position = match.end()
            continue

        close = "</draw:%s>" % match.group("tag")
        inner = text[match.end():end - len(close)]
        out.append(text[position:match.end()])
        out.append(_shape_holds(match.group("tag"), inner, _escaped(str(incoming))))
        out.append(close)
        position = end

    out.append(text[position:])
    return "".join(out).encode("utf-8")


def _shape_holds(tag, inner, escaped):
    """A shape's body with its text replaced. A frame keeps its text in a text box; the box is
    where the paragraphs are, and a frame with no box — an image — has no text to write."""
    if tag != "frame":
        return _paragraphs_hold(inner, escaped)

    box = _TEXT_BOX.search(inner)
    if box is None:
        return inner
    box_end = _element_end(inner, "text-box", box.end())
    if box_end < 0:
        return inner
    close = "</draw:text-box>"
    return (inner[:box.end()]
            + _paragraphs_hold(inner[box.end():box_end - len(close)], escaped)
            + inner[box_end - len(close):])


def _paragraphs_hold(body, escaped):
    """The first paragraph carries the value, in its first span when it has one; the rest go."""
    paragraphs = list(_PARAGRAPH.finditer(body))
    if not paragraphs:
        return body + "<text:p>" + escaped + "</text:p>"

    first = paragraphs[0]
    attributes = first.group("attributes").rstrip().rstrip("/")
    inner = first.group("inner")
    span = _SPAN.search(inner) if inner else None
    if span is None:
        replaced = "<text:p%s>%s</text:p>" % (attributes, escaped)
    else:
        span_attributes = span.group("attributes").rstrip().rstrip("/")
        replaced = "<text:p%s><text:span%s>%s</text:span></text:p>" % (attributes, span_attributes, escaped)

    rest = _PARAGRAPH.sub("", body[first.end():])
    return body[:first.start()] + replaced + rest


def _element_end(text, tag, start):
    """Where the ``draw:<tag>`` element opened just before ``start`` ends — the index after its
    closing tag — counting nested elements of the same name, or -1 when it never closes."""
    opening = re.compile(r'<draw:%s\b[^>]*?(?<!/)>' % re.escape(tag))
    closing = "</draw:%s>" % tag
    depth = 1
    position = start
    while depth:
        close_at = text.find(closing, position)
        if close_at < 0:
            return -1
        nested = opening.search(text, position, close_at)
        if nested is not None:
            depth += 1
            position = nested.end()
        else:
            depth -= 1
            position = close_at + len(closing)
    return position


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
