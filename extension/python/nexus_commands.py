"""The functions LibreOffice calls when a Nexus PLM toolbar button or menu item is used.

One function per command, each named in ``Addons.xcu``. The set is the Word add-in's, minus the two
that have no meaning here (Markup and Apply Markups, which are about Word's comments and tracked
changes) and the Navigator pane, which needs a docked WebView the office does not offer.

They are deliberately thin: every command asks the service to do the work, because the service owns
the session, the dialogs and the toasts. The only things decided here are the ones only the host can
know — which document is in front of the user, whether it has unsaved edits, what this host is able
to open, and what the document's fields currently hold.

Every function catches everything. An exception escaping into UNO is reported to the user as an
unhelpful scripting error, and in the worst case takes the frame down with it.
"""

import os
import traceback
import webbrowser

# The ``nexusplm`` package lives in ``pythonpath/`` beside this file. That folder name is a
# LibreOffice convention: the script provider adds it to sys.path before running anything here.
# It is the only way to find the package, because the provider exec()s this module and sets
# ``__file__`` only afterwards — at import time the name does not exist at all.
from nexusplm import document as doc
from nexusplm import state
from nexusplm.client import Client, ServiceUnavailable

_LOG = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"),
    "NexusPLM", "Logs", "plmlibreofficeaddin.log")

HELP_URL = "https://github.com/Nexus-PLM"


def _log(message):
    """A line in the same place every other Nexus add-in logs.

    Best effort: a command must not fail because a log file could not be written.
    """
    try:
        os.makedirs(os.path.dirname(_LOG), exist_ok=True)
        with open(_LOG, "a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except Exception:
        pass


def _client():
    return Client()


def _say(client, message, severity="info"):
    """Tells the user something, through the one toast the tray host owns."""
    try:
        client.notify(message, severity)
    except Exception:
        _log("could not post a notification: " + message)


def _refused(client, answer, command):
    """Shows the service's own reason for refusing, or a plain line when it gave none.

    A cancelled dialog is not a refusal and says nothing.
    """
    if answer.get("cancelled"):
        return
    _say(client, answer.get("error") or "Nexus PLM did not answer the %s request." % command,
         "warning")


def _command(name):
    """Wraps a command so nothing escapes into UNO and every outcome is logged."""
    def decorate(function):
        def run(*args):
            _log("%s: started" % name)
            try:
                result = function(*args)
                _log("%s: done" % name)
                return result
            except ServiceUnavailable as unavailable:
                _log("%s: %s" % (name, unavailable))
                # No service means no toast either, so this one has to be said locally.
                _message_box(str(unavailable))
            except Exception:
                _log("%s: failed\n%s" % (name, traceback.format_exc()))
        run.__name__ = function.__name__
        run.__doc__ = function.__doc__
        return run
    return decorate


def _message_box(text, question=False):
    """The only dialogs this add-in shows itself.

    One is for when the service is unreachable, so it cannot show anything. The other is the one
    question only the host can ask — "discard your unsaved edits?" — because only the host knows
    there are any. Everything else the user sees comes from the tray host, which is what keeps one
    look across Word, Excel, PowerPoint, FreeCAD and LibreOffice.

    Returns True when a question was answered yes.
    """
    try:
        context = XSCRIPTCONTEXT.getComponentContext()          # noqa: F821
        toolkit = context.ServiceManager.createInstanceWithContext(
            "com.sun.star.awt.Toolkit", context)
        parent = XSCRIPTCONTEXT.getDesktop().getCurrentFrame().getContainerWindow()  # noqa: F821
        # MessageBoxType: 1 = INFOBOX, 3 = QUERYBOX. Buttons: 1 = OK, 3 = YES_NO. Result: 2 = YES.
        box = toolkit.createMessageBox(parent, 3 if question else 1, 3 if question else 1,
                                       "Nexus PLM", text)
        return box.execute() == 2
    except Exception:
        _log("could not show a message box: " + text)
        return False


def _here():
    """The document in front of the user, its path, and a handle to parent a dialog to."""
    context = XSCRIPTCONTEXT.getComponentContext()               # noqa: F821
    document = doc.current(context)
    return context, document, doc.path_of(document), doc.window_handle(document)


def _item_of(client, path):
    """The PLM item a document is, or ``None`` when it is not registered.

    What this add-in wrote down when it last handled the file comes first, because asking the
    service by path does not answer the question: ``/plm/state?file_path=`` searches the Engine for
    an object carrying that path as an attribute, and on a live server that search finds nothing —
    not for a document created seconds earlier, not for one checked in months ago. The path is
    still asked about when nothing is remembered, so a path the service can resolve still works.
    """
    if not path:
        return None

    remembered = state.item_of(path)
    if remembered:
        # Confirm it with PLM rather than trusting the note: the item may have been deleted, and
        # the answer carries the current status anyway.
        answer = client.state(item_id=remembered)
        if answer.get("success") and answer.get("item_id"):
            return answer["item_id"]
        state.forget(path)

    answer = client.state(file_path=path)
    if answer.get("success") and answer.get("item_id"):
        _remember(path, answer)
        return answer["item_id"]
    return None


def _remember(path, answer):
    """Writes down which item a file is, from whatever the service just answered about it."""
    item_id = answer.get("item_id") or answer.get("plm_object_id")
    if path and item_id:
        state.remember(path, item_id,
                       part_number=answer.get("part_number"),
                       object_id=answer.get("object_id") or answer.get("plm_object_id"))


def _require_item(client, path):
    item_id = _item_of(client, path)
    if item_id is None:
        _say(client, "This document is not registered in PLM.", "warning")
    return item_id


def _require_path(client, path):
    if not path:
        _say(client, "Save the document first, so there is a file to work with.", "warning")
    return path


def _open_with_values(context, client, answer, command):
    """Opens the file the service staged and writes its values into it.

    The service writes nothing into a document itself — it does not know the format — so the
    values it hands back are written here, into the user fields the template already has.
    """
    staged = answer.get("file_path")
    if not staged:
        _say(client, "That item has no document in the vault.", "warning")
        return None

    # Which item this file is, before anything else: every PLM command keys off the path, and a
    # staged file the add-in opened without writing that down is a file on which every command
    # then refuses. The Office add-ins learned this one the same way.
    _remember(staged, answer)

    opened = doc.open_staged(context, staged)
    written = doc.write_user_fields(opened, answer.get("attribute_mappings") or {})
    _log("%s: opened '%s' as %s, wrote %d field(s)"
         % (command, staged, state.item_of(staged) or "an unknown item", written))
    return opened


# ── account ─────────────────────────────────────────────────────────────────

@_command("SignIn")
def sign_in(*_args):
    """Shows the service's sign-in window, or says who is already signed in."""
    client = _client()
    who = client.me()
    if who.get("success"):
        _say(client, "Signed in as %s." % (who.get("username") or "you"))
        return

    _, _document, _path, hwnd = _here()
    answer = client.sign_in(hwnd)
    if answer.get("success"):
        _say(client, "Signed in as %s." % (answer.get("username") or "you"))
    else:
        _refused(client, answer, "Sign In")


@_command("SignOut")
def sign_out(*_args):
    client = _client()
    answer = client.sign_out()
    if answer.get("success"):
        _say(client, "Signed out.")
    else:
        _refused(client, answer, "Sign Out")


# ── data management ─────────────────────────────────────────────────────────

@_command("New")
def new_from_template(*_args):
    """Creates a PLM item from a template and opens it, checked out to you."""
    client = _client()
    context, _document, _path, hwnd = _here()

    answer = client.new(hwnd, file_extensions=doc.OPENABLE_EXTENSIONS)
    if not answer.get("success"):
        return _refused(client, answer, "New")

    _open_with_values(context, client, answer, "New")


@_command("Open")
def open_from_plm(*_args):
    """Picks an item in PLM, stages its file, and opens it."""
    client = _client()
    context, _document, _path, hwnd = _here()

    answer = client.open_document(hwnd, file_extensions=doc.OPENABLE_EXTENSIONS,
                                  stage_assembly=False)
    if not answer.get("success"):
        return _refused(client, answer, "Open")

    _open_with_values(context, client, answer, "Open")


@_command("Search")
def search(*_args):
    """Advanced Search over document types; opening a result stages and opens it."""
    client = _client()
    context, _document, _path, hwnd = _here()

    answer = client.search(hwnd)
    if not answer.get("success"):
        return _refused(client, answer, "Search")
    if not answer.get("file_path"):
        return   # closed without choosing anything

    _open_with_values(context, client, answer, "Search")


@_command("Save")
def save_to_plm(*_args):
    """Saves the document and uploads it to the vault, keeping the lock."""
    client = _client()
    _context, document, path, _hwnd = _here()
    if not _require_path(client, path):
        return
    item_id = _require_item(client, path)
    if item_id is None:
        return

    if doc.is_modified(document) and not doc.save(document):
        return _say(client, "The document could not be saved, so it was not uploaded.", "warning")

    answer = client.save(item_id, path)
    if not answer.get("success"):
        _refused(client, answer, "Save")


@_command("SaveAsNew")
def save_as_new(*_args):
    """Registers this document as a new PLM item."""
    client = _client()
    _context, document, path, hwnd = _here()
    if not _require_path(client, path):
        return

    if doc.is_modified(document) and not doc.save(document):
        return _say(client, "The document could not be saved, so it was not registered.", "warning")

    answer = client.save_as_new(path, hwnd, attributes=doc.user_fields(document),
                                file_extensions=doc.OPENABLE_EXTENSIONS)
    if not answer.get("success"):
        return _refused(client, answer, "Save As")

    # This file is that item from now on. Registering it and then not writing that down is how a
    # document PLM had just created came back as "not registered in PLM" on the next command.
    _remember(path, answer)

    # Registering allocates the number PLM chose; the document should show it.
    doc.write_user_fields(document, answer.get("attribute_mappings") or {})


@_command("SaveAsExisting")
def save_as_existing(*_args):
    """Gives this document's content to an existing PLM item."""
    client = _client()
    _context, document, path, hwnd = _here()
    if not _require_path(client, path):
        return

    if doc.is_modified(document) and not doc.save(document):
        return _say(client, "The document could not be saved, so it was not uploaded.", "warning")

    answer = client.save_as_existing(path, hwnd, file_extensions=doc.OPENABLE_EXTENSIONS)
    if not answer.get("success"):
        return _refused(client, answer, "Save As Existing")

    # The document now belongs to the item the user picked, not to whatever it was before.
    _remember(path, answer)


# ── tasks ───────────────────────────────────────────────────────────────────

@_command("CheckOut")
def check_out(*_args):
    """Takes the lock on the open document."""
    client = _client()
    _context, _document, path, _hwnd = _here()
    item_id = _require_item(client, path)
    if item_id is None:
        return

    answer = client.check_out(item_id)
    if not answer.get("success"):
        _refused(client, answer, "Check Out")


@_command("CheckIn")
def check_in(*_args):
    """Saves the document if it has unsaved edits, then uploads it and releases the lock.

    Check In means "publish what I have", so it saves first rather than asking — uploading a
    version that does not match what the user is looking at is the failure this has been bitten by
    more than once. It tells the service it saved, so the user is told too.
    """
    client = _client()
    _context, document, path, _hwnd = _here()
    item_id = _require_item(client, path)
    if item_id is None:
        return

    saved_first = doc.is_modified(document)
    if saved_first and not doc.save(document):
        return _say(client, "The document could not be saved, so it was not checked in.", "warning")

    answer = client.check_in(item_id, path, saved_unsaved_changes=saved_first)
    if not answer.get("success"):
        _refused(client, answer, "Check In")


@_command("Release")
def release(*_args):
    """Promotes the revision to Released."""
    client = _client()
    _context, _document, path, _hwnd = _here()
    item_id = _require_item(client, path)
    if item_id is None:
        return

    answer = client.release(item_id)
    if not answer.get("success"):
        _refused(client, answer, "Release")


@_command("Revise")
def revise(*_args):
    """Creates the next revision from a released one and opens it."""
    client = _client()
    context, _document, path, _hwnd = _here()
    item_id = _require_item(client, path)
    if item_id is None:
        return

    answer = client.revise(item_id)
    if not answer.get("success"):
        return _refused(client, answer, "Revise")

    if answer.get("file_path"):
        _open_with_values(context, client, answer, "Revise")


@_command("ChangeOwner")
def change_owner(*_args):
    """Transfers the item, and its lock if there is one, to another user."""
    client = _client()
    _context, _document, path, hwnd = _here()
    item_id = _require_item(client, path)
    if item_id is None:
        return

    answer = client.change_owner(item_id, hwnd, path)
    if not answer.get("success"):
        _refused(client, answer, "Change Ownership")


# ── workflow ────────────────────────────────────────────────────────────────

@_command("Worklist")
def worklist(*_args):
    """Opens your worklist."""
    client = _client()
    _context, _document, _path, hwnd = _here()
    answer = client.worklist(hwnd)
    if not answer.get("success"):
        _refused(client, answer, "Worklist")


@_command("NewWorkflow")
def new_workflow(*_args):
    """Starts a workflow on this document."""
    client = _client()
    _context, _document, path, _hwnd = _here()
    item_id = _require_item(client, path)
    if item_id is None:
        return

    answer = client.new_workflow(item_id)
    if not answer.get("success"):
        _refused(client, answer, "New Workflow")


# ── attribute exchange ──────────────────────────────────────────────────────

@_command("Properties")
def properties(*_args):
    """Shows the item's detail window."""
    client = _client()
    _context, _document, path, hwnd = _here()
    item_id = _require_item(client, path)
    if item_id is None:
        return

    client.properties(item_id, hwnd)


@_command("EditValues")
def edit_values(*_args):
    """Edits the item's attributes in the service's dialog, then writes the saved values back."""
    client = _client()
    _context, document, path, hwnd = _here()
    item_id = _require_item(client, path)
    if item_id is None:
        return

    answer = client.edit_values(item_id, hwnd, doc.user_fields(document))
    if not answer.get("success"):
        return _refused(client, answer, "Edit Values")
    if answer.get("saved"):
        doc.write_user_fields(document, answer.get("attribute_mappings") or {})


@_command("RefreshValues")
def refresh_values(*_args):
    """Re-reads the item's attributes from PLM into the document's fields."""
    client = _client()
    _context, document, path, _hwnd = _here()
    item_id = _require_item(client, path)
    if item_id is None:
        return

    answer = client.refresh_values(item_id)
    if not answer.get("success"):
        return _refused(client, answer, "Refresh Values")

    written = doc.write_user_fields(document, answer.get("attribute_mappings") or {})
    if written == 0:
        # Worth saying: a document whose template names none of the attributes looks exactly
        # like a command that silently did nothing.
        _say(client, "Nothing to update: this document has no fields matching the item's attributes.")


@_command("ReloadDocument")
def reload_document(*_args):
    """Replaces this copy with the vault's latest.

    Unsaved edits are the user's to lose, so they are asked — and asked before the document is
    closed, because a replacement refused after that leaves them with neither copy.
    """
    client = _client()
    context, document, path, _hwnd = _here()
    item_id = _require_item(client, path)
    if item_id is None:
        return

    if doc.is_modified(document) and not _message_box(
            "This document has unsaved changes. Discard them and reload from PLM?", question=True):
        return

    answer = client.reload_document(item_id)
    if not answer.get("success"):
        return _refused(client, answer, "Reload Document")

    doc.close_without_saving(document)
    _open_with_values(context, client, answer, "Reload")


# ── settings and about ──────────────────────────────────────────────────────

@_command("Settings")
def settings(*_args):
    client = _client()
    client.settings()


@_command("About")
def about(*_args):
    client = _client()
    _context, _document, _path, hwnd = _here()
    client.about(hwnd, addin_version=doc.ADDIN_VERSION)


@_command("Help")
def help_site(*_args):
    webbrowser.open(HELP_URL)


@_command("ConnectionStatus")
def connection_status(*_args):
    """Says whether the service is reachable and who is signed in."""
    client = _client()
    client.health()          # raises ServiceUnavailable, which the wrapper reports
    who = client.me()
    if who.get("success"):
        _say(client, "Connected to Nexus PLM. Signed in as %s." % (who.get("username") or "you"))
    else:
        _say(client, "Connected to Nexus PLM. Nobody is signed in.")


# What LibreOffice is allowed to call. Anything not listed is not a command.
g_exportedScripts = (
    sign_in, sign_out,
    new_from_template, open_from_plm, search, save_to_plm, save_as_new, save_as_existing,
    check_out, check_in, release, revise, change_owner,
    worklist, new_workflow,
    properties, edit_values, refresh_values, reload_document,
    settings, about, help_site, connection_status,
)
