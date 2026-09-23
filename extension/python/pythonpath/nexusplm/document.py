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


def date_parts(text):
    """``(year, month, day)`` from a date, or ``None`` when the text is not one.

    Accepts what PLM sends — an ISO date, with or without a time after it — and nothing else. The
    closed-file connector takes the same shapes; the two paths have to agree, or a value written
    while the document is open would differ from the same value written while it is closed.
    """
    text = (text or "").strip()
    if not text:
        return None

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
    return year, month, day


def time_parts(text):
    """``(hours, minutes, seconds)`` from a clock time or an xsd duration, or ``None``."""
    text = (text or "").strip()
    if not text:
        return None

    if text.upper().startswith("PT"):
        body, numbers = text[2:].upper(), {}
        digits = ""
        for character in body:
            if character.isdigit() or character == ".":
                digits += character
            elif character in "HMS" and digits:
                numbers[character] = float(digits)
                digits = ""
            else:
                return None
        if not numbers:
            return None
        return int(numbers.get("H", 0)), int(numbers.get("M", 0)), int(numbers.get("S", 0))

    parts = text.split(":")
    if len(parts) not in (2, 3):
        return None
    try:
        numbers = [int(float(part)) for part in parts]
    except ValueError:
        return None
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers)


#: What PLM sends for a boolean. A checkbox arrives as "True"/"False" from the service and as
#: "true"/"false" from the file, and a person editing a value types "yes".
_TRUE = {"true", "yes", "y", "1"}
_FALSE = {"false", "no", "n", "0"}


def boolean_value(text):
    """``True``/``False``, or ``None`` when the text is not a boolean."""
    text = (text or "").strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return None


def number_value(text):
    """The number, or ``None``. The decimal point is the invariant one, as ODF stores it."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


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


def typed_value(type_name, text):
    """PLM's text as the type the property holds, or ``None`` to leave the property alone.

    The service deals in text; a document property has a type, and a typed one refuses text it
    cannot hold. Handing every property ``str(value)`` is what the first version did, and it wrote
    seven of the twelve fields of the tracking document: the two dates, the review date, the
    checkbox and the number were all silently skipped, so the typed half of a type never reached
    the page.

    ``None`` means "not a value of this type" — an empty string is not a date, and blanking a
    typed field would lose the template author's value. That is the same decision
    ``OdfValueWrite.Decide`` makes for a closed file.
    """
    import uno   # only reachable inside an office, and only needed for the struct types

    text = "" if text is None else str(text)
    short = type_name.rsplit(".", 1)[-1].lower()

    if short in ("string", "any"):
        return text

    if short == "boolean":
        return boolean_value(text)

    if short in ("double", "float", "long", "short", "hyper"):
        number = number_value(text)
        if number is None:
            return None
        return number if short in ("double", "float") else int(number)

    if short in ("date", "datetime"):
        parts = date_parts(text)
        if parts is None:
            return None
        year, month, day = parts
        value = uno.createUnoStruct("com.sun.star.util." + ("Date" if short == "date" else "DateTime"))
        value.Year, value.Month, value.Day = year, month, day
        if short == "datetime":
            clock = time_parts(text.split("T")[1]) if "T" in text else None
            value.Hours, value.Minutes, value.Seconds = clock or (0, 0, 0)
        return value

    if short == "time":
        clock = time_parts(text)
        if clock is None:
            return None
        value = uno.createUnoStruct("com.sun.star.util.Time")
        value.Hours, value.Minutes, value.Seconds = clock
        return value

    if short == "duration":
        clock = time_parts(text)
        if clock is None:
            return None
        value = uno.createUnoStruct("com.sun.star.util.Duration")
        value.Hours, value.Minutes, value.Seconds = clock
        return value

    return text


def write_user_fields(document, values):
    """Writes PLM's values into the user-defined properties the document already has.

    Only fields the document already carries are written — a field nobody put in the template is
    not a field of it — and each is written as the type that property holds. Returns how many were
    written. The document is marked modified so the change is saved with it.
    """
    if not values:
        return 0

    written = 0
    try:
        container = document.getDocumentProperties().getUserDefinedProperties()
        info = container.getPropertySetInfo()
        wanted = {k.lower(): v for k, v in values.items()}

        for prop in info.getProperties():
            text = wanted.get(prop.Name.lower())
            if text is None:
                continue

            value = typed_value(prop.Type.typeName, text)
            if value is None:
                # Not a value of that type. Leaving the property alone is the same decision the
                # closed-file connector makes, and is why an empty value never blanks a typed field.
                continue

            try:
                container.setPropertyValue(prop.Name, value)
                written += 1
            except Exception:
                # The property refused it after all. One field is not worth losing the rest.
                pass

        if written:
            document.setModified(True)
    except Exception:
        pass
    return written
