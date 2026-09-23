"""How PLM's text becomes the type a document property holds.

The service deals in text; a document property has a type, and a typed one refuses text it cannot
hold. Handing every property ``str(value)`` wrote seven of the tracking document's twelve fields —
both dates, the review date, the checkbox and the number were silently skipped.

The parsing is pure, so it is checked here; assembling the UNO structs needs an office and is the
thin part above it.

    python -m unittest discover -s tests/python
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), "..", "..", "extension", "python", "pythonpath"))

from nexusplm import document  # noqa: E402


class Dates(unittest.TestCase):
    def test_what_plm_sends(self):
        for text in ("2026-10-15", "2026-10-15T00:00:00", "2026-10-15 09:30:00", "2026/10/15"):
            self.assertEqual((2026, 10, 15), document.date_parts(text), text)

    def test_an_empty_value_is_not_a_date(self):
        """A typed field an empty value would blank keeps the template author's value."""
        self.assertIsNone(document.date_parts(""))
        self.assertIsNone(document.date_parts("   "))
        self.assertIsNone(document.date_parts(None))

    def test_text_that_is_not_a_date(self):
        for text in ("next Tuesday", "2026-13-01", "2026-10-32", "2026-10", "15/10/2026/1"):
            self.assertIsNone(document.date_parts(text), text)


class Times(unittest.TestCase):
    def test_a_clock_time(self):
        self.assertEqual((1, 30, 0), document.time_parts("01:30:00"))
        self.assertEqual((9, 5, 0), document.time_parts("09:05"))

    def test_an_xsd_duration_which_is_what_odf_stores(self):
        self.assertEqual((1, 30, 0), document.time_parts("PT1H30M0S"))
        self.assertEqual((0, 45, 0), document.time_parts("PT45M"))

    def test_text_that_is_not_a_time(self):
        for text in ("", "half past", "PT", "1:2:3:4"):
            self.assertIsNone(document.time_parts(text), text)


class Booleans(unittest.TestCase):
    def test_the_spellings_that_reach_here(self):
        """The service sends Python's "True"; a file holds "true"; a person types "yes"."""
        for text in ("True", "true", "TRUE", "yes", "y", "1"):
            self.assertIs(True, document.boolean_value(text), text)
        for text in ("False", "false", "no", "n", "0"):
            self.assertIs(False, document.boolean_value(text), text)

    def test_anything_else_leaves_the_checkbox_alone(self):
        for text in ("", "maybe", "2"):
            self.assertIsNone(document.boolean_value(text), text)


class Numbers(unittest.TestCase):
    def test_a_number(self):
        self.assertEqual(4.5, document.number_value("4.5"))
        self.assertEqual(7.0, document.number_value(" 7 "))
        self.assertEqual(-2.0, document.number_value("-2"))

    def test_anything_else(self):
        for text in ("", "high", "4,5"):
            self.assertIsNone(document.number_value(text), text)


class TheTrackingDocument(unittest.TestCase):
    """Every field of the document the type describes, through the rule that writes it."""

    def test_each_value_is_or_is_not_a_value_of_its_type(self):
        cases = [
            ("PartNumber", "string", "LTD-00000002-ODT", True),
            ("Revision", "string", "A", True),
            ("Description", "string", "Second run, linked fields", True),
            ("CreationDate", "date", "2026-09-22", True),
            ("ModificationDate", "date", "2026-09-22T18:02:00", True),
            ("ReviewDue", "date", "2026-10-15", True),
            ("Approved", "boolean", "True", True),
            ("Priority", "double", "7", True),
            # and the cases that must leave the template's value where it is
            ("ReviewDue", "date", "", False),
            ("Priority", "double", "", False),
            ("Approved", "boolean", "", False),
        ]
        for name, kind, text, writable in cases:
            parsed = {
                "string": lambda t: t,
                "date": document.date_parts,
                "boolean": document.boolean_value,
                "double": document.number_value,
            }[kind](text)
            self.assertEqual(writable, parsed is not None, "%s = %r" % (name, text))


if __name__ == "__main__":
    unittest.main()
