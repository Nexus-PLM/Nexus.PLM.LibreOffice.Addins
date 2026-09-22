"""HTTP client for the Nexus PLM Addin Service (``http://localhost:5100``).

The service is the only thing this add-in talks to. It never reaches the Engine or the Vault
directly: the service owns the session, the dialogs and the toasts, and it is the piece that already
knows how to name a staged dataset, how to check something out, and what to say when it fails.

Standard library only. LibreOffice bundles its own Python and we do not control what is installed in
it, so ``requests`` is not available and must not be assumed — ``urllib`` is.
"""

import json
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE_URL = "http://localhost:5100"

# Long enough for a command that puts a dialog in front of the user and waits for them, short
# enough that a service which is not running fails rather than hanging the application.
DIALOG_TIMEOUT = 600
QUICK_TIMEOUT = 10


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
                return {"success": False, "error": "The service refused the request (HTTP %d)."
                        % error.code}
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

    # ── session ──────────────────────────────────────────────────────────────

    def health(self):
        """Whether the service is up. Raises :class:`ServiceUnavailable` when it is not."""
        return self._get("/api/health")

    def me(self):
        """Who is signed in, if anyone: ``{"success": bool, "username": ...}``.

        The flag really is called ``success`` — the service's MeResponse(bool Success, string?
        Username). The SDK once looked for ``is_logged_in``, a field the service never sends, and so
        reported every signed-in session as signed out. Read the actual contract.
        """
        return self._get("/api/auth/me")

    def sign_in(self, hwnd=0):
        """Shows the service's sign-in window. Answers ``{"success", "username"}``."""
        return self._post("/api/auth/login", {"hwnd": hwnd}, timeout=DIALOG_TIMEOUT)

    # ── what this document is ────────────────────────────────────────────────

    def state(self, file_path=None, item_id=None):
        """What PLM knows about a document, by path or by item."""
        return self._get("/plm/state", file_path=file_path, item_id=item_id)

    # ── the commands ─────────────────────────────────────────────────────────

    def open_document(self, hwnd=0, file_extensions=None, stage_assembly=False):
        """Shows the browser and stages whatever the user picks.

        ``file_extensions`` is how a host says what it can open — the service keeps no list of
        hosts. ``stage_assembly`` is false because a document has no assembly to load; that panel
        appearing over a text document was the CAD flow bleeding into it.
        """
        return self._post(
            "/plm/open",
            {
                "hwnd": hwnd,
                "file_extensions": file_extensions,
                "stage_assembly": stage_assembly,
            },
            timeout=DIALOG_TIMEOUT,
        )

    def check_out(self, item_id):
        return self._post("/plm/checkout", {"item_id": item_id})

    def check_in(self, item_id, file_path, saved_unsaved_changes=False):
        """Uploads the file and releases the lock.

        ``saved_unsaved_changes`` is the one thing only the host knows: whether it had to save the
        user's edits first. The service words the toast from it, so that a user whose unsaved work
        was just committed to the vault is told.
        """
        # CheckInRequest(ItemId, FilePath, IsAssembly, Structure, Joints, SavedUnsavedChanges):
        # the structure fields are for CAD assemblies and are empty for a document, but the
        # record declares them without defaults, so they are sent rather than omitted.
        return self._post(
            "/plm/checkin",
            {
                "item_id": item_id,
                "file_path": file_path,
                "is_assembly": False,
                "structure": [],
                "joints": [],
                "saved_unsaved_changes": saved_unsaved_changes,
            },
            timeout=DIALOG_TIMEOUT,
        )

    def properties(self, item_id, hwnd=0):
        return self._post("/plm/properties", {"item_id": item_id, "hwnd": hwnd},
                          timeout=DIALOG_TIMEOUT)

    def edit_values(self, item_id, hwnd=0, document_values=None):
        return self._post(
            "/plm/edit-values",
            {"item_id": item_id, "hwnd": hwnd, "document_values": document_values or {}},
            timeout=DIALOG_TIMEOUT,
        )

    def refresh_values(self, item_id):
        return self._post("/plm/refresh-values", {"item_id": item_id})

    def notify(self, title, message, severity="info"):
        """Posts a toast for something only this host knows.

        Same endpoint and body as the Word client's PostNotificationAsync, so LibreOffice's toasts
        look like everyone else's.
        """
        return self._post(
            "/api/notification",
            {
                "title": title,
                "description": message,
                "severity": severity,
                "is_dismissible": True,
                "auto_dismiss_after_seconds": 5,
            },
        )
