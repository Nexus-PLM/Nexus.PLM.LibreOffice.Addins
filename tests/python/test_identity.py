"""Which PLM item a document is, and why the order of the two questions matters.

This is a regression suite before it is anything else. The toolbar and the sidebar each had their
own answer to the same question, and they disagreed: the toolbar asked the note the add-in had
written down and only then the service, while the sidebar asked the service by path and nothing
else. Driving Calc on Sep 26 2026 showed the result — a spreadsheet registered as AUD-000014
seconds earlier, with a working toolbar beside a panel headed "This document is not in PLM" and
every button greyed.

    python -m unittest discover -s tests/python
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), "..", "..", "extension", "python", "pythonpath"))

from nexusplm import identity
from nexusplm import state as notes


class FakeClient:
    """Answers /plm/state the way the real service does, and records what it was asked."""

    def __init__(self, by_item=None, by_path=None):
        self._by_item = by_item or {}
        self._by_path = by_path or {}
        self.asked = []

    def state(self, file_path=None, item_id=None):
        if item_id is not None:
            self.asked.append(("item_id", item_id))
            return self._by_item.get(item_id, {"success": False})
        self.asked.append(("file_path", file_path))
        return self._by_path.get(file_path, {"success": False})


def answer(item_id, part_number="AUD-000014"):
    return {"success": True, "item_id": item_id, "part_number": part_number,
            "status": "checked_out", "object_id": item_id}


class ResolvingADocument(unittest.TestCase):

    def setUp(self):
        # The note store is a file; keep each test to its own.
        self._path = notes._PATH
        notes._PATH = os.path.join(os.path.dirname(__file__), "identity-test-notes.json")
        if os.path.exists(notes._PATH):
            os.remove(notes._PATH)

    def tearDown(self):
        if os.path.exists(notes._PATH):
            os.remove(notes._PATH)
        notes._PATH = self._path

    def test_a_document_registered_where_it_sat_is_still_found(self):
        """The case that was broken, and the reason this module exists.

        Save As New registers a document under its own name, so the file is called
        calc-host-test.ods and the item is AUD-000014. ``/plm/state?file_path=`` resolves by the
        part number IN THE FILE NAME, so it cannot answer for this file at all. Only the note can.
        """
        path = os.path.abspath("calc-host-test.ods")
        notes.remember(path, "item-1", part_number="AUD-000014")
        client = FakeClient(by_item={"item-1": answer("item-1")})

        self.assertEqual("item-1", identity.item_of(client, path))
        self.assertEqual(("item_id", "item-1"), client.asked[0])

    def test_the_note_is_asked_before_the_path(self):
        path = os.path.abspath("thing.odt")
        notes.remember(path, "item-1")
        client = FakeClient(by_item={"item-1": answer("item-1")},
                            by_path={path: answer("item-2")})

        self.assertEqual("item-1", identity.item_of(client, path))
        self.assertNotIn(("file_path", path), client.asked)

    def test_a_note_the_service_no_longer_honours_is_dropped(self):
        """The item may have been deleted since. A stale note must not pin a document to it."""
        path = os.path.abspath("gone.odt")
        notes.remember(path, "deleted-item")
        client = FakeClient()

        self.assertIsNone(identity.item_of(client, path))
        self.assertIsNone(notes.item_of(path), "the dead note is forgotten")

    def test_a_path_the_service_can_resolve_still_works_and_is_written_down(self):
        """A file PLM staged IS named by its part number, so the path question answers it."""
        path = os.path.abspath("AUD-000014.ods")
        client = FakeClient(by_path={path: answer("item-9")})

        self.assertEqual("item-9", identity.item_of(client, path))
        self.assertEqual("item-9", notes.item_of(path), "so the next question costs nothing")

    def test_an_unregistered_document_is_not_an_item_and_does_not_throw(self):
        self.assertIsNone(identity.item_of(FakeClient(), os.path.abspath("stranger.odt")))
        self.assertIsNone(identity.item_of(FakeClient(), None))
        self.assertEqual({}, identity.state_of(FakeClient(), None))

    def test_state_of_returns_the_whole_answer_because_the_panel_shows_it(self):
        # item_of throws away everything but the id; the panel needs the status and the owner.
        path = os.path.abspath("full.ods")
        notes.remember(path, "item-1")
        client = FakeClient(by_item={"item-1": answer("item-1")})

        state = identity.state_of(client, path)
        self.assertEqual("checked_out", state.get("status"))
        self.assertEqual("AUD-000014", state.get("part_number"))


class BothCallersUseTheSameRule(unittest.TestCase):
    """A rule two callers each implement is a rule that will differ again."""

    def test_neither_the_toolbar_nor_the_panel_asks_by_path_alone(self):
        root = os.path.join(os.path.dirname(__file__), "..", "..", "extension", "python")
        for name in ("nexus_commands.py", "nexusplm_sidebar.py"):
            with open(os.path.join(root, name), encoding="utf-8") as handle:
                source = handle.read()
            self.assertNotIn("client.state(file_path=", source,
                             name + " resolves a document by path alone, which cannot answer for "
                                    "a document registered under its own name")
            self.assertIn("identity.", source, name + " must use the shared rule")


if __name__ == "__main__":
    unittest.main()
