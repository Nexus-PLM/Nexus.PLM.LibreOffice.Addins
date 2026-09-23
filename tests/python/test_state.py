"""Which PLM item each document is, as this add-in remembers it.

Asking the service by file path does not answer that question — ``/plm/state?file_path=`` searches
the Engine for an object carrying the path as an attribute and finds nothing, for a document
created seconds earlier as much as for one checked in months ago — so every command refused with
"This document is not registered in PLM." The add-in writes it down instead, as the Office
add-ins do.

    python -m unittest discover -s tests/python
"""

import importlib
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), "..", "..", "extension", "python", "pythonpath"))


class TheDocumentMap(unittest.TestCase):
    def setUp(self):
        self._appdata = os.environ.get("APPDATA")
        os.environ["APPDATA"] = tempfile.mkdtemp(prefix="nexus-state-")
        # The module reads APPDATA once, at import.
        from nexusplm import state
        self.state = importlib.reload(state)

    def tearDown(self):
        if self._appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self._appdata

    def test_a_file_is_the_item_it_was_told_it_is(self):
        self.state.remember(r"C:\Nexus\Staging\LTD-00000002-ODT.odt", "rev-uuid", part_number="LTD-00000002-ODT")

        self.assertEqual("rev-uuid", self.state.item_of(r"C:\Nexus\Staging\LTD-00000002-ODT.odt"))
        self.assertEqual("LTD-00000002-ODT",
                         self.state.known(r"C:\Nexus\Staging\LTD-00000002-ODT.odt")["part_number"])

    def test_the_same_file_written_differently_is_the_same_file(self):
        """Windows paths differ in case and in separators; the document does not."""
        self.state.remember(r"C:\Nexus\Staging\LTD-1.odt", "rev-uuid")

        self.assertEqual("rev-uuid", self.state.item_of(r"c:\nexus\staging\ltd-1.odt"))
        self.assertEqual("rev-uuid", self.state.item_of("C:/Nexus/Staging/LTD-1.odt"))

    def test_a_file_nobody_has_registered(self):
        self.assertIsNone(self.state.item_of(r"C:\Users\someone\Documents\notes.odt"))
        self.assertEqual({}, self.state.known(r"C:\Users\someone\Documents\notes.odt"))
        self.assertIsNone(self.state.item_of(None))

    def test_forgetting_one_leaves_the_others(self):
        self.state.remember(r"C:\Nexus\Staging\A.odt", "rev-a")
        self.state.remember(r"C:\Nexus\Staging\B.odt", "rev-b")

        self.assertTrue(self.state.forget(r"C:\Nexus\Staging\A.odt"))

        self.assertIsNone(self.state.item_of(r"C:\Nexus\Staging\A.odt"))
        self.assertEqual("rev-b", self.state.item_of(r"C:\Nexus\Staging\B.odt"))

    def test_forgetting_what_was_never_known(self):
        self.assertFalse(self.state.forget(r"C:\Nexus\Staging\never.odt"))

    def test_a_document_saved_elsewhere_keeps_its_item(self):
        self.state.remember(r"C:\Nexus\Staging\LTD-1.odt", "rev-uuid", part_number="LTD-1")

        self.assertTrue(self.state.rename(r"C:\Nexus\Staging\LTD-1.odt", r"C:\Users\me\Desktop\LTD-1.odt"))

        self.assertIsNone(self.state.item_of(r"C:\Nexus\Staging\LTD-1.odt"))
        self.assertEqual("rev-uuid", self.state.item_of(r"C:\Users\me\Desktop\LTD-1.odt"))

    def test_writing_it_down_survives_the_add_in_being_reloaded(self):
        """Every command runs in a fresh interpreter state; the map has to be on disk."""
        self.state.remember(r"C:\Nexus\Staging\LTD-1.odt", "rev-uuid")

        from nexusplm import state
        reloaded = importlib.reload(state)

        self.assertEqual("rev-uuid", reloaded.item_of(r"C:\Nexus\Staging\LTD-1.odt"))

    def test_a_damaged_map_is_an_empty_one(self):
        """A map that cannot be read must cost the commands nothing but a lookup."""
        self.state.remember(r"C:\Nexus\Staging\LTD-1.odt", "rev-uuid")
        with open(self.state._PATH, "w", encoding="utf-8") as handle:
            handle.write("{ this is not json")

        self.assertIsNone(self.state.item_of(r"C:\Nexus\Staging\LTD-1.odt"))
        self.assertTrue(self.state.remember(r"C:\Nexus\Staging\LTD-2.odt", "rev-2"))
        self.assertEqual("rev-2", self.state.item_of(r"C:\Nexus\Staging\LTD-2.odt"))


if __name__ == "__main__":
    unittest.main()
