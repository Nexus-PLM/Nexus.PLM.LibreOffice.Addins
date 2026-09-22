"""The functions LibreOffice calls when a Nexus PLM toolbar button or menu item is used.

One function per command, each named in ``Addons.xcu``. They are deliberately thin: every command
asks the service to do the work, because the service owns the session, the dialogs and the toasts.
The only things decided here are the ones only the host can know — which document is in front of
the user, whether it has unsaved edits, and what this host is able to open.

Every function catches everything. An exception escaping into UNO is reported to the user as an
unhelpful scripting error, and in the worst case takes the frame down with it.
"""

import os
import traceback

# The ``nexusplm`` package lives in ``pythonpath/`` beside this file. That folder name is a
# LibreOffice convention: the script provider adds it to sys.path before running anything here.
# It is the only way to find the package, because the provider exec()s this module and sets
# ``__file__`` only afterwards — at import time the name does not exist at all.
from nexusplm import document as doc
from nexusplm.client import Client, ServiceUnavailable

_LOG = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"),
    "NexusPLM", "Logs", "plmlibreofficeaddin.log")


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
        client.notify("Nexus PLM", message, severity)
    except Exception:
        _log("could not post a notification: " + message)


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


def _message_box(text):
    """The only dialog this add-in shows itself: the service is unreachable, so it cannot.

    Everything else the user sees comes from the tray host, which is what keeps one look across
    Word, Excel, PowerPoint, FreeCAD and LibreOffice.
    """
    try:
        context = XSCRIPTCONTEXT.getComponentContext()          # noqa: F821
        toolkit = context.ServiceManager.createInstanceWithContext(
            "com.sun.star.awt.Toolkit", context)
        parent = XSCRIPTCONTEXT.getDesktop().getCurrentFrame().getContainerWindow()  # noqa: F821
        box = toolkit.createMessageBox(
            parent, 1, 1, "Nexus PLM", text)   # INFOBOX, BUTTONS_OK
        box.execute()
    except Exception:
        _log("could not show a message box: " + text)


def _here():
    """The document in front of the user, its path, and a handle to parent a dialog to."""
    context = XSCRIPTCONTEXT.getComponentContext()               # noqa: F821
    document = doc.current(context)
    return context, document, doc.path_of(document), doc.window_handle(document)


def _item_of(client, path):
    """The PLM item a document is, or ``None`` when it is not registered."""
    if not path:
        return None
    state = client.state(file_path=path)
    return state.get("item_id") if state.get("success") else None


# ── the commands ────────────────────────────────────────────────────────────

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
    elif answer.get("error"):
        _say(client, answer["error"], "warning")


@_command("Open")
def open_from_plm(*_args):
    """Picks an item in PLM, stages its file, and opens it."""
    client = _client()
    context, _document, _path, hwnd = _here()

    answer = client.open_document(
        hwnd=hwnd,
        file_extensions=doc.OPENABLE_EXTENSIONS,
        stage_assembly=False)

    if answer.get("cancelled"):
        return
    if not answer.get("success"):
        _say(client, answer.get("error") or "Nexus PLM did not answer the Open request.", "warning")
        return

    staged = answer.get("file_path")
    if not staged:
        _say(client, "That item has no document in the vault.", "warning")
        return

    doc.open_staged(context, staged)


@_command("CheckOut")
def check_out(*_args):
    """Takes the lock on the open document."""
    client = _client()
    _context, _document, path, _hwnd = _here()

    item_id = _item_of(client, path)
    if item_id is None:
        _say(client, "This document is not registered in PLM.", "warning")
        return

    answer = client.check_out(item_id)
    if not answer.get("success"):
        _say(client, answer.get("error") or "Nexus PLM did not answer the Check Out request.",
             "warning")


@_command("CheckIn")
def check_in(*_args):
    """Saves the document if it has unsaved edits, then uploads it and releases the lock.

    Check In means "publish what I have", so it saves first rather than asking — uploading a version
    that does not match what the user is looking at is the failure this has been bitten by more than
    once. It tells the service it saved, so the user is told too.
    """
    client = _client()
    _context, document, path, _hwnd = _here()

    item_id = _item_of(client, path)
    if item_id is None:
        _say(client, "This document is not registered in PLM.", "warning")
        return

    saved_first = doc.is_modified(document)
    if saved_first and not doc.save(document):
        _say(client, "The document could not be saved, so it was not checked in.", "warning")
        return

    answer = client.check_in(item_id, path, saved_unsaved_changes=saved_first)
    if not answer.get("success") and not answer.get("cancelled"):
        _say(client, answer.get("error") or "Nexus PLM did not answer the Check In request.",
             "warning")


@_command("Properties")
def properties(*_args):
    """Shows the item's detail window."""
    client = _client()
    _context, _document, path, hwnd = _here()

    item_id = _item_of(client, path)
    if item_id is None:
        _say(client, "This document is not registered in PLM.", "warning")
        return

    client.properties(item_id, hwnd)


@_command("EditValues")
def edit_values(*_args):
    """Shows the item's mapped attributes, and hands over what the document currently holds."""
    client = _client()
    _context, document, path, hwnd = _here()

    item_id = _item_of(client, path)
    if item_id is None:
        _say(client, "This document is not registered in PLM.", "warning")
        return

    client.edit_values(item_id, hwnd, doc.user_fields(document))


@_command("RefreshValues")
def refresh_values(*_args):
    """Re-reads the item's attributes from PLM into the document."""
    client = _client()
    _context, _document, path, _hwnd = _here()

    item_id = _item_of(client, path)
    if item_id is None:
        _say(client, "This document is not registered in PLM.", "warning")
        return

    answer = client.refresh_values(item_id)
    if not answer.get("success"):
        _say(client, answer.get("error") or "Nexus PLM did not answer the Refresh Values request.",
             "warning")


# What LibreOffice is allowed to call. Anything not listed is not a command.
g_exportedScripts = (
    sign_in,
    open_from_plm,
    check_out,
    check_in,
    properties,
    edit_values,
    refresh_values,
)
