"""What the sidebar panel shows, decided without LibreOffice anywhere near it.

The panel itself is UNO plumbing — a container window, some labels, some buttons — and none of
that can be tested without an office running. What can be tested is every decision it makes: which
rows to show, what to put in them when a value is missing, which buttons a document in this state
may use, and what to say when there is no document at all. Those live here, as functions over the
answer ``/plm/state`` gives, so the panel is left with nothing to get wrong on its own.
"""

#: The rows, in the order a person reads them: identity first, then where it is in its life, then
#: who is holding it. Each entry is (label, key in the state answer).
ROWS = (
    ("Part number", "part_number"),
    ("Revision",    "revision"),
    ("Status",      "status"),
    ("Checked out", "checked_out_by"),
    ("Type",        "type_name"),
    ("Description", "description"),
)

#: Shown in place of a value the server did not send. An empty cell reads as a bug; this does not.
ABSENT = "—"

#: What the panel says when the document in front of it is not a PLM item. This is the ordinary
#: case for a file someone just created, so it is phrased as a fact and not as a failure.
NOT_IN_PLM = "This document is not in PLM."

#: And when there is no document open at all.
NO_DOCUMENT = "No document is open."


def _status_word(status):
    """The lifecycle word as a person says it: ``checked_out`` is "Checked out"."""
    if not status:
        return ABSENT
    return status.replace("_", " ").capitalize()


def rows_for(state):
    """The (label, value) pairs to display for a ``/plm/state`` answer.

    Every row is always present. A panel whose rows appear and disappear as values arrive makes the
    thing underneath the cursor move, and the row a user is reading is the one they lose.
    """
    if not state:
        return [(label, ABSENT) for label, _ in ROWS]

    out = []
    for label, key in ROWS:
        value = state.get(key)
        if key == "status":
            value = _status_word(value)
        out.append((label, value if value else ABSENT))
    return out


def is_in_plm(state):
    """Whether the answer describes a document PLM actually knows.

    ``status`` is ``unknown`` both for a file PLM has never seen and for one it could not resolve,
    so this is deliberately about what can be shown, not about why.
    """
    return bool(state) and bool(state.get("status")) and state["status"] != "unknown"


def headline(state, has_document=True):
    """The one line at the top of the panel, above the rows."""
    if not has_document:
        return NO_DOCUMENT
    if not is_in_plm(state):
        return NOT_IN_PLM
    return state.get("part_number") or ABSENT


#: The disclosure marks on the document section's header. Text, not icons: a UNO button takes a
#: label and nothing else, and these read the same on every platform the add-in runs on.
OPEN_MARK = "▾"     # ▾
CLOSED_MARK = "▸"   # ▸

#: The document half starts folded. The navigator is what the panel is mostly for — the rows
#: below repeat what the document itself already shows, and the tree is the part that needs the
#: height. Opening the section is one click, and it stays open for as long as the panel lives.
STARTS_COLLAPSED = True


def document_header(state, collapsed, has_document=True):
    """The document section's header line: its disclosure mark, and what is behind it.

    Folded, this is the only thing naming the document, so it carries the headline rather than a
    fixed word like "Document" — a collapsed panel that cannot tell you which item you have open
    would be worth less than no panel.
    """
    mark = CLOSED_MARK if collapsed else OPEN_MARK
    return "%s %s" % (mark, headline(state, has_document))


#: Each button: (label, the command in nexus_commands.py, when it may be pressed).
#: The rule matches the toolbar's, because a user who sees a command in two places and finds it
#: enabled in one of them has found a bug, whichever one is right.
BUTTONS = (
    ("Check Out",   "check_out",     "checked_in"),
    ("Check In",    "check_in",      "mine"),
    ("Save to PLM", "save_to_plm",   "mine"),
    ("Edit Values", "edit_values",   "in_plm"),
    ("Refresh",     "refresh_values", "in_plm"),
)


def enabled_buttons(state, user=None):
    """Which buttons may be pressed for this state, as a set of command names.

    ``user`` is who is signed in; a document checked out to somebody else is not yours to check in,
    and the panel must not offer it — the service would refuse, and an offer that is always refused
    is worse than no offer.
    """
    if not is_in_plm(state):
        return set()

    status = state.get("status")
    holder = state.get("checked_out_by")
    mine   = status == "checked_out" and bool(user) and holder == user

    allowed = set()
    for _, command, rule in BUTTONS:
        if rule == "in_plm":
            allowed.add(command)
        elif rule == "checked_in" and status == "checked_in":
            allowed.add(command)
        elif rule == "mine" and mine:
            allowed.add(command)
    return allowed
