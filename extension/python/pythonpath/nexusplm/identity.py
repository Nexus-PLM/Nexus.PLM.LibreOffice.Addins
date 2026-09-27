"""Which PLM item a document on disk is — the one resolution rule, in one place.

This exists because there are two callers and they disagreed. The toolbar asked the note this
add-in had written down and only then asked the service; the sidebar asked the service by path and
nothing else. So a document the add-in had registered seconds earlier showed a full toolbar and a
panel that said "This document is not in PLM", with every button greyed.

The order matters and is not an optimisation:

``/plm/state?file_path=`` resolves a document by the **part number in its file name**, because
every dataset the vault stages is named by its part number. That works for a file PLM handed over
and not for one PLM adopted where it already sat — Save As New registers a document under its own
name, so `calc-host-test.ods` is item AUD-000014 and its name says nothing about that. The note
this add-in wrote is the only thing that knows.

The note is confirmed against the service rather than trusted: the item may have been deleted since,
and the answer carries the current status anyway. A note that no longer resolves is dropped, so a
stale one cannot keep a document pinned to an item that is gone.
"""

from nexusplm import state as notes


def remember(path, answer):
    """Writes down which item a file is, from whatever the service just answered about it."""
    item_id = answer.get("item_id") or answer.get("plm_object_id")
    if path and item_id:
        notes.remember(path, item_id,
                       part_number=answer.get("part_number"),
                       object_id=answer.get("object_id") or answer.get("plm_object_id"))


def state_of(client, path):
    """What PLM knows about the document at ``path``.

    Returns the service's answer. An answer whose ``success`` is false, or which carries no
    ``item_id``, means the document is not a PLM item as far as this machine can tell.
    """
    if not path:
        return {}

    remembered = notes.item_of(path)
    if remembered:
        answer = client.state(item_id=remembered)
        if answer.get("success") and answer.get("item_id"):
            return answer
        notes.forget(path)

    answer = client.state(file_path=path)
    if answer.get("success") and answer.get("item_id"):
        remember(path, answer)
    return answer


def item_of(client, path):
    """The PLM item a document is, or ``None`` when it is not registered."""
    answer = state_of(client, path)
    if answer.get("success") and answer.get("item_id"):
        return answer["item_id"]
    return None
