"""What the sidebar panel decides to show, and which of its buttons a document may use.

The panel is a docked deck built from UNO controls, so the drawing of it cannot be tested without
an office running. Every decision behind it can be, and is here: which rows exist, what fills a row
whose value the server did not send, what the headline says for a document PLM has never seen, and
which commands a document in a given state is allowed to be offered.

The button rules matter more than they look. A command offered in the panel but refused by the
service is worse than one not offered at all — the user presses it, nothing happens, and they have
learned the add-in lies. So these hold the panel to the same rule the toolbar follows.

    python -m unittest discover -s tests/python
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), "..", "..", "extension", "python", "pythonpath"))

from nexusplm import panel


def state(**overrides):
    """A ``/plm/state`` answer for a document PLM knows, with anything overridden per test."""
    answer = {
        "status": "checked_in",
        "part_number": "LTD-00000009-ODT",
        "revision": "A.003",
        "checked_out_by": None,
        "type_name": "n5LibreOfficeTrackingDoc",
        "description": "Every field, in the file",
    }
    answer.update(overrides)
    return answer


class TheRows(unittest.TestCase):
    def test_every_row_is_always_present(self):
        # A panel whose rows appear and vanish as values arrive moves what is under the cursor,
        # and the row being read is the one that gets lost.
        full = panel.rows_for(state())
        empty = panel.rows_for(None)

        self.assertEqual(len(full), len(panel.ROWS))
        self.assertEqual(len(empty), len(panel.ROWS))
        self.assertEqual([label for label, _ in full], [label for label, _ in empty])

    def test_a_value_the_server_did_not_send_reads_as_absent_not_blank(self):
        rows = dict(panel.rows_for(state(description=None, checked_out_by=None)))

        self.assertEqual(rows["Description"], panel.ABSENT)
        self.assertEqual(rows["Checked out"], panel.ABSENT)

    def test_the_status_is_shown_the_way_a_person_says_it(self):
        rows = dict(panel.rows_for(state(status="checked_out")))

        self.assertEqual(rows["Status"], "Checked out")

    def test_values_are_shown_as_they_came(self):
        rows = dict(panel.rows_for(state()))

        self.assertEqual(rows["Part number"], "LTD-00000009-ODT")
        self.assertEqual(rows["Revision"], "A.003")


class TheHeadline(unittest.TestCase):
    def test_names_the_part_number_for_a_document_plm_knows(self):
        self.assertEqual(panel.headline(state()), "LTD-00000009-ODT")

    def test_says_so_plainly_when_the_document_is_not_in_plm(self):
        # The ordinary case for a file someone just created, so it is phrased as a fact.
        self.assertEqual(panel.headline({"status": "unknown"}), panel.NOT_IN_PLM)
        self.assertEqual(panel.headline(None), panel.NOT_IN_PLM)

    def test_says_so_when_nothing_is_open_at_all(self):
        self.assertEqual(panel.headline(None, has_document=False), panel.NO_DOCUMENT)


class WhichButtonsMayBePressed(unittest.TestCase):
    def test_a_document_not_in_plm_offers_nothing(self):
        self.assertEqual(panel.enabled_buttons({"status": "unknown"}, "admin"), set())
        self.assertEqual(panel.enabled_buttons(None, "admin"), set())

    def test_a_checked_in_document_may_be_checked_out(self):
        allowed = panel.enabled_buttons(state(status="checked_in"), "admin")

        self.assertIn("check_out", allowed)
        self.assertNotIn("check_in", allowed)
        self.assertNotIn("save_to_plm", allowed)

    def test_a_document_checked_out_to_me_may_be_saved_and_checked_in(self):
        mine = state(status="checked_out", checked_out_by="admin")
        allowed = panel.enabled_buttons(mine, "admin")

        self.assertIn("check_in", allowed)
        self.assertIn("save_to_plm", allowed)
        self.assertNotIn("check_out", allowed)

    def test_a_document_checked_out_to_someone_else_is_not_mine_to_check_in(self):
        # The service would refuse it, and an offer that is always refused teaches the user that
        # the panel cannot be trusted.
        theirs = state(status="checked_out", checked_out_by="jdoe")
        allowed = panel.enabled_buttons(theirs, "admin")

        self.assertNotIn("check_in", allowed)
        self.assertNotIn("save_to_plm", allowed)
        self.assertNotIn("check_out", allowed)

    def test_nobody_signed_in_means_nothing_is_mine(self):
        out = state(status="checked_out", checked_out_by="admin")

        self.assertNotIn("check_in", panel.enabled_buttons(out, None))

    def test_anything_in_plm_may_have_its_values_read(self):
        # Edit Values and Refresh ask the service, which enforces its own rules; showing them for
        # any known document is what the toolbar does.
        for status in ("checked_in", "checked_out", "released"):
            allowed = panel.enabled_buttons(state(status=status), "admin")
            self.assertIn("edit_values", allowed, status)
            self.assertIn("refresh_values", allowed, status)


class WhatTheButtonsAre(unittest.TestCase):
    def test_every_button_names_a_command_the_add_in_exports(self):
        # A button whose command does not exist fails silently inside LibreOffice: the dispatch
        # finds no handler and nothing at all happens.
        commands = os.path.join(os.path.dirname(__file__), "..", "..",
                                "extension", "python", "nexus_commands.py")
        with open(commands, encoding="utf-8") as handle:
            source = handle.read()

        for _label, command, _rule in panel.BUTTONS:
            self.assertIn("def %s(" % command, source,
                          "the panel offers %s, which nexus_commands.py does not export" % command)


class DocumentHeader(unittest.TestCase):
    """The document half folds away; its header is what is left when it is folded."""

    def test_folded_it_still_names_the_item(self):
        # The only thing on screen naming the open document, so a fixed word like "Document"
        # would make a collapsed panel worth less than no panel.
        state = {"status": "checked_in", "part_number": "LTD-00000009-ODT"}

        self.assertEqual("▸ LTD-00000009-ODT",
                         panel.document_header(state, collapsed=True))

    def test_open_it_shows_the_other_mark(self):
        state = {"status": "checked_in", "part_number": "LTD-00000009-ODT"}

        self.assertEqual("▾ LTD-00000009-ODT",
                         panel.document_header(state, collapsed=False))

    def test_a_document_plm_does_not_know_says_so_in_the_header(self):
        self.assertEqual("▸ " + panel.NOT_IN_PLM,
                         panel.document_header(None, collapsed=True))

    def test_no_document_at_all_says_so_in_the_header(self):
        self.assertEqual("▸ " + panel.NO_DOCUMENT,
                         panel.document_header(None, collapsed=True, has_document=False))

    def test_it_starts_folded(self):
        # The navigator is what the panel is mostly for; the rows repeat what the document
        # already shows. Marc asked for this directly.
        self.assertTrue(panel.STARTS_COLLAPSED)


if __name__ == "__main__":
    unittest.main()
