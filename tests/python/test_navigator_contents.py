"""A folder in the navigator can be opened, and what is inside it can be seen.

Marc, Sep 26 2026: "the navigator is not showing content but it shows numbers". It drew the folder
tree with the server's own counts beside each name and there was no way to open one: a folder with
no SUB-folders was built as a leaf, so "My Working (10)" advertised ten documents and offered no
handle to see them. ``item_label`` had been written for exactly this and was never called.

These hold the two halves that were missing — which folders can be opened, and what a document's
line says — with no LibreOffice anywhere near them.

    python -m unittest discover -s tests/python
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), "..", "..", "extension", "python", "pythonpath"))

from nexusplm import navigator


def folder(folder_id, name, parent=None, count=0, order=0):
    return {"folder_id": folder_id, "name": name, "parent_id": parent,
            "object_count": count, "sort_order": order}


class WhichFoldersCanBeOpened(unittest.TestCase):

    def test_a_folder_holding_only_documents_can_still_be_opened(self):
        """The bug. Ten documents, no sub-folders, and it was drawn as a leaf."""
        tree = navigator.tree_from([folder("mine", "My Working", count=10)])

        self.assertEqual("My Working (10)", tree[0]["label"])
        self.assertTrue(navigator.holds_anything(tree[0]))

    def test_a_folder_with_sub_folders_can_be_opened_whatever_its_count(self):
        tree = navigator.tree_from([folder("top", "Top"), folder("sub", "Sub", parent="top")])

        self.assertTrue(navigator.holds_anything(tree[0]))

    def test_a_folder_with_neither_is_a_leaf(self):
        # Offering a handle that opens onto nothing is its own small lie.
        tree = navigator.tree_from([folder("empty", "Empty")])

        self.assertFalse(navigator.holds_anything(tree[0]))

    def test_a_node_with_nothing_in_it_at_all_does_not_throw(self):
        self.assertFalse(navigator.holds_anything({}))
        self.assertFalse(navigator.holds_anything({"children": [], "folder": None}))


class WhatADocumentsLineSays(unittest.TestCase):

    def test_the_part_number_and_its_revision(self):
        self.assertEqual("AUD-000014  A",
                         navigator.item_label({"part_number": "AUD-000014", "revision": "A"}))

    def test_a_document_with_no_revision_yet(self):
        self.assertEqual("AUD-000014", navigator.item_label({"part_number": "AUD-000014"}))

    def test_a_document_the_server_named_badly_still_gets_a_line(self):
        # A blank line in a tree is unreadable and unclickable; a labelled one can be reported.
        self.assertEqual("(no part number)", navigator.item_label({}))
        self.assertEqual("(no part number)", navigator.item_label({"part_number": "   "}))


class ThePanelWiresItUp(unittest.TestCase):
    """The rules above are worth nothing if the panel never asks them."""

    def setUp(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..",
                            "extension", "python", "nexusplm_sidebar.py")
        with open(path, encoding="utf-8") as handle:
            self.source = handle.read()

    def test_the_tree_asks_which_folders_can_be_opened(self):
        self.assertIn("navigator_rules.holds_anything", self.source)

    def test_opening_a_folder_lists_its_documents(self):
        self.assertIn("def requestChildNodes", self.source)
        self.assertIn("folder_items", self.source)
        self.assertIn("navigator_rules.item_label", self.source)

    def test_the_tree_listens_for_a_folder_being_opened(self):
        # Without the listener requestChildNodes is never called and the handle opens onto nothing.
        self.assertIn("addTreeExpansionListener", self.source)
        self.assertIn("XTreeExpansionListener", self.source)


if __name__ == "__main__":
    unittest.main()
