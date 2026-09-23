"""Which PLM item each document on this machine is.

Every PLM command needs to know what the document in front of the user is. Asking the service by
file path does not answer it: ``/plm/state?file_path=`` searches the Engine for an object carrying
that path as an attribute, and on a live server that search returns nothing — for a document this
add-in had created a moment earlier, and for a Word document that has been checked in for months.
Everything then refuses with "This document is not registered in PLM."

So the add-in records it, the way the Office add-ins do (``PlmDocumentState`` there): every handler
that learns which item a file is writes it down, keyed by the file's path, and every handler that
needs one reads it back. The service is still asked when nothing is remembered, so a path the
service *can* resolve still works.

The file is small, per user, and rewritten atomically — a half-written map would lose every
document at once. Nothing here is a cache of PLM's truth: it holds an identifier, and the current
status is always asked of the service with it.
"""

import json
import os
import tempfile

#: Where the map lives. Beside the add-in's log, under the user's roaming profile.
_FOLDER = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "NexusPLM")
_PATH = os.path.join(_FOLDER, "libreoffice-documents.json")


def _key(path):
    """The map's key for a path: absolute, and case-insensitively the same file on Windows."""
    return os.path.normcase(os.path.abspath(path))


def _read():
    try:
        with open(_PATH, encoding="utf-8") as handle:
            loaded = json.load(handle)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        # A missing or damaged map is an empty one: the commands then ask the service, which is
        # exactly what happens the first time anybody runs this.
        return {}


def _write(everything):
    try:
        os.makedirs(_FOLDER, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=_FOLDER, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(everything, out, indent=1)
        os.replace(temporary, _PATH)   # atomic: readers see the old map or the new one
        return True
    except Exception:
        try:
            os.unlink(temporary)
        except Exception:
            pass
        return False


def remember(path, item_id, part_number=None, object_id=None):
    """Records that ``path`` is this item. Returns whether it was written."""
    if not path or not item_id:
        return False

    everything = _read()
    entry = {"item_id": item_id}
    if part_number:
        entry["part_number"] = part_number
    if object_id:
        entry["object_id"] = object_id
    everything[_key(path)] = entry
    return _write(everything)


def known(path):
    """What is remembered about ``path``, as a dict, or ``{}``."""
    if not path:
        return {}
    return _read().get(_key(path), {})


def item_of(path):
    """The item ``path`` is, or ``None`` when nothing is remembered about it."""
    return known(path).get("item_id")


def forget(path):
    """Drops what is remembered about ``path`` — used when PLM says it is not that item."""
    if not path:
        return False

    everything = _read()
    if everything.pop(_key(path), None) is None:
        return False
    return _write(everything)


def rename(old_path, new_path):
    """Follows a document that was saved somewhere else, keeping its item."""
    entry = known(old_path)
    if not entry:
        return False

    everything = _read()
    everything.pop(_key(old_path), None)
    everything[_key(new_path)] = entry
    return _write(everything)
