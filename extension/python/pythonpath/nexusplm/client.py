"""HTTP client for the Nexus PLM Addin Service (``http://localhost:5100``).

The service is the only thing this add-in talks to. It never reaches the Engine or the Vault
directly: the service owns the session, the dialogs and the toasts, and it is the piece that already
knows how to name a staged dataset, how to check something out, and what to say when it fails.

Every request shape here was read from the service's ``PlmModels.cs`` and the Word client, not
guessed. The first version of this file guessed four of them and every one was wrong.

Standard library only. LibreOffice bundles its own Python and we do not control what is installed in
it, so ``requests`` is not available and must not be assumed — ``urllib`` is.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "http://localhost:5100"

#: What this host is called, in the New dialog's template chip and in the service's log.
HOST_NAME = "LibreOffice"

#: The base type the New, Search and Save As dialogs are limited to. Documents, not parts.
ROOT_BASE_TYPE = "DocumentsBase"

# Long enough for a command that puts a dialog in front of the user and waits for them, short
# enough that a service which is not running fails rather than hanging the application.
#: A call that opens a dialog waits for a person, and a person may take their time. Ten minutes
#: was not enough: a Settings window left open longer than that reported the command as failed,
#: for a dialog that then saved perfectly well. A service that has died is a different thing and is
#: noticed at once — the socket closes, which is an error of its own, not a timeout.
DIALOG_TIMEOUT = 3600
QUICK_TIMEOUT = 15


class ServiceUnavailable(Exception):
    """The service could not be reached at all — usually the tray host is not running."""


class Client:
    """One call per method, each answering a plain dict.

    A refused call is not an exception: the service answers ``{"success": false, "error": ...}`` and
    every caller shows that. Only a service that cannot be reached raises, because that is the one
    failure the user has to fix themselves.
    """

    def __init__(self, base_url=DEFAULT_BASE_URL):
        self.base_url = base_url.rstrip("/")

    # ── plumbing ─────────────────────────────────────────────────────────────

    def _call(self, method, path, body=None, timeout=QUICK_TIMEOUT):
        url = self.base_url + path
        data = json.dumps(body).encode("utf-8") if body is not None else None

        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw.strip() else {}
        except urllib.error.HTTPError as error:
            # The service answers its own failures in the body; a status alone is not the story.
            try:
                return json.loads(error.read().decode("utf-8"))
            except Exception:
                return {"success": False,
                        "error": "The service refused the request (HTTP %d)." % error.code}
        except urllib.error.URLError as error:
            raise ServiceUnavailable(
                "Nexus PLM is not running. Start the Nexus PLM Addins tray application."
            ) from error

    def _get(self, path, timeout=QUICK_TIMEOUT, **query):
        clean = {k: v for k, v in query.items() if v is not None}
        if clean:
            path = path + "?" + urllib.parse.urlencode(clean)
        return self._call("GET", path, timeout=timeout)

    def _post(self, path, body, timeout=QUICK_TIMEOUT):
        return self._call("POST", path, body, timeout=timeout)

    def _dialog(self, path, body):
        return self._post(path, body, timeout=DIALOG_TIMEOUT)

    # ── session ──────────────────────────────────────────────────────────────

    def health(self):
        """Whether the service is up. Raises :class:`ServiceUnavailable` when it is not."""
        return self._get("/api/health")

    def me(self):
        """Who is signed in: ``{"success": bool, "username": ...}``.

        The flag really is called ``success`` — the service's ``MeResponse(bool Success, string?
        Username)``. The SDK once looked for ``is_logged_in``, a field the service never sends, and
        so reported every signed-in session as signed out.
        """
        return self._get("/api/auth/me")

    def sign_in(self, hwnd=0):
        """Shows the service's sign-in window. Answers ``{"success", "username"}``."""
        return self._dialog("/api/auth/login", {"hwnd": hwnd})

    def sign_out(self):
        return self._post("/api/auth/logout", {})

    # ── what this document is ────────────────────────────────────────────────

    def state(self, file_path=None, item_id=None):
        """What PLM knows about a document, by path or by item."""
        return self._get("/plm/state", file_path=file_path, item_id=item_id)

    # ── data management ──────────────────────────────────────────────────────

    def new(self, hwnd=0, file_extensions=None):
        """Creates an item from a template. The service stages the file and hands back its path.

        ``host_name`` is declared, not inferred: the New dialog's template chip and note name the
        host from it. ``file_extensions`` limits the type list to templates this host can open.
        """
        return self._dialog("/plm/new", {
            "root_base_type": ROOT_BASE_TYPE,
            "hwnd": hwnd,
            "host_name": HOST_NAME,
            "file_extensions": file_extensions,
        })

    def open_document(self, hwnd=0, file_extensions=None, stage_assembly=False):
        """Shows the browser and stages whatever the user picks.

        ``file_extensions`` is how a host says what it can open — the service keeps no list of
        hosts. ``stage_assembly`` is false because a document has no assembly to load; that panel
        appearing over a text document was the CAD flow bleeding into it.
        """
        return self._dialog("/plm/open", {
            "hwnd": hwnd,
            "root_base_type": ROOT_BASE_TYPE,
            "file_extensions": file_extensions,
            "stage_assembly": stage_assembly,
        })

    def search(self, hwnd=0):
        """Advanced Search, limited to document types. Answers the picked item and its staged file."""
        return self._dialog("/plm/search", {"root_base_type": ROOT_BASE_TYPE, "hwnd": hwnd})

    def save(self, item_id, file_path):
        """Uploads the file without releasing the lock."""
        return self._post("/plm/save", {"item_id": item_id, "file_path": file_path},
                          timeout=DIALOG_TIMEOUT)

    def save_as_new(self, file_path, hwnd=0, attributes=None, file_extensions=None):
        """Registers this file as a new item. The document's own field values are offered as
        defaults for the new item's attributes."""
        return self._dialog("/plm/save-as-new", {
            "file_path": file_path,
            "hwnd": hwnd,
            "attributes": attributes or {},
            "root_base_type": ROOT_BASE_TYPE,
            "host_name": HOST_NAME,
            "file_extensions": file_extensions,
        })

    def save_as_existing(self, file_path, hwnd=0, file_extensions=None):
        """Gives this file's content to an existing item the user picks."""
        return self._dialog("/plm/save-as-existing", {
            "file_path": file_path,
            "hwnd": hwnd,
            "root_base_type": ROOT_BASE_TYPE,
            "file_extensions": file_extensions,
        })

    # ── tasks ────────────────────────────────────────────────────────────────

    def check_out(self, item_id):
        return self._post("/plm/checkout", {"item_id": item_id}, timeout=DIALOG_TIMEOUT)

    def check_in(self, item_id, file_path, saved_unsaved_changes=False):
        """Uploads the file and releases the lock.

        ``saved_unsaved_changes`` is the one thing only the host knows: whether it had to save the
        user's edits first. The service words the toast from it, so that a user whose unsaved work
        was just committed to the vault is told.

        ``CheckInRequest(ItemId, FilePath, IsAssembly, Structure, Joints, SavedUnsavedChanges)``: the
        structure fields are for CAD assemblies and are empty for a document, but the record
        declares them without defaults, so they are sent rather than omitted.
        """
        return self._dialog("/plm/checkin", {
            "item_id": item_id,
            "file_path": file_path,
            "is_assembly": False,
            "structure": [],
            "joints": [],
            "saved_unsaved_changes": saved_unsaved_changes,
        })

    def release(self, item_id):
        return self._post("/plm/release", {"item_id": item_id}, timeout=DIALOG_TIMEOUT)

    def revise(self, item_id, hwnd=0):
        """Creates the next revision. Answers the new item's id, revision and staged file.

        The window handle parents the choice of major or minor, which the service asks for when
        the type allows both.
        """
        return self._post("/plm/revise", {"item_id": item_id, "hwnd": hwnd},
                          timeout=DIALOG_TIMEOUT)

    def change_owner(self, item_id, hwnd=0, file_path=None):
        return self._dialog("/plm/set-owner",
                            {"item_id": item_id, "hwnd": hwnd, "file_path": file_path})

    # ── workflow ─────────────────────────────────────────────────────────────

    def worklist(self, hwnd=0):
        return self._dialog("/plm/worklist", {"hwnd": hwnd})

    def new_workflow(self, item_id):
        return self._post("/plm/workflow", {"item_id": item_id}, timeout=DIALOG_TIMEOUT)

    # ── attribute exchange ───────────────────────────────────────────────────

    def properties(self, item_id, hwnd=0):
        return self._dialog("/plm/properties", {"item_id": item_id, "hwnd": hwnd})

    def edit_values(self, item_id, hwnd=0, document_values=None):
        return self._dialog("/plm/edit-values", {
            "item_id": item_id, "hwnd": hwnd, "document_values": document_values or {},
        })

    def refresh_values(self, item_id):
        return self._post("/plm/refresh-values", {"item_id": item_id})

    def reload_document(self, item_id):
        return self._post("/plm/reload-document", {"item_id": item_id}, timeout=DIALOG_TIMEOUT)

    # ── settings and about ───────────────────────────────────────────────────

    def settings(self):
        return self._dialog("/plm/settings", {})

    def about(self, hwnd=0, addin_version=None):
        return self._dialog("/plm/about", {
            "hwnd": hwnd, "host_name": HOST_NAME, "addin_version": addin_version,
        })

    # ── navigator ────────────────────────────────────────────────────────────

    def folders(self):
        """Every folder the signed-in user may read: ``{"success", "folders": [...]}``.

        One flat list, each folder carrying its own ``parent_id``; :mod:`nexusplm.navigator`
        turns that into the tree. These are reads, so unlike every other ``/plm`` call they
        raise no toast and open no sign-in window — a signed-out user gets an empty answer and
        the panel says so.
        """
        return self._get("/plm/navigation/folders", timeout=DIALOG_TIMEOUT)

    def folder_items(self, folder_id):
        """What is in one folder: ``{"success", "items": [...]}``."""
        return self._get("/plm/navigation/folders/%s/items" % urllib.parse.quote(str(folder_id)),
                         timeout=DIALOG_TIMEOUT)

    def lookup(self, query):
        """Items matching a part number or name: ``{"success", "items": [...]}``."""
        return self._get("/plm/navigation/lookup", q=query, timeout=DIALOG_TIMEOUT)

    def notify(self, message, severity="info"):
        """Posts a toast for something only this host knows.

        Same endpoint and body as the Word client's ``PostNotificationAsync``, so LibreOffice's
        toasts look like everyone else's.
        """
        return self._post("/api/notification", {
            "title": "Nexus PLM",
            "description": message,
            "severity": severity,
            "is_dismissible": True,
            "auto_dismiss_after_seconds": 5,
        })
