"""Reading a document's properties back as the text ODF stores.

A typed property comes back from UNO as a struct. ``str()`` on one renders its repr, and Edit
Values put this in front of the user as a review date:

    scr(com.sun.star.util.Date){ Day = (unsigned short)0x18, Month = (unsigned short)0xc, ...

Saving would have written that to PLM. These are the lexical forms ``OdfValueWrite`` writes into a
closed file, so an open document and a closed one read the same.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), "..", "..", "extension", "python", "pythonpath"))

from nexusplm import document  # noqa: E402


class FakeStruct:
    """Stands in for a com.sun.star.util struct: fields, and a repr that must never be the value."""

    def __init__(self, **fields):
        self.__dict__.update(fields)

    def __str__(self):
        return "scr(com.sun.star.util.Date){ " + ", ".join(
            "%s = %r" % item for item in sorted(self.__dict__.items())) + " }"


class TypedValues(unittest.TestCase):
    def test_a_date(self):
        self.assertEqual("2026-12-24T00:00:00",
                         document.text_of(FakeStruct(Year=2026, Month=12, Day=24)))

    def test_a_date_and_time(self):
        self.assertEqual(
            "2026-09-22T18:02:30",
            document.text_of(FakeStruct(Year=2026, Month=9, Day=22, Hours=18, Minutes=2, Seconds=30)))

    def test_a_duration(self):
        self.assertEqual("PT1H30M0S", document.text_of(FakeStruct(Hours=1, Minutes=30, Seconds=0)))

    def test_a_boolean(self):
        """ODF spells it lower case, and Python's "True" is not that."""
        self.assertEqual("true", document.text_of(True))
        self.assertEqual("false", document.text_of(False))

    def test_a_number(self):
        self.assertEqual("7", document.text_of(7.0), "the number seven is not '7.0'")
        self.assertEqual("4.5", document.text_of(4.5))
        self.assertEqual("3", document.text_of(3))

    def test_a_string_and_nothing(self):
        self.assertEqual("Engineering", document.text_of("Engineering"))
        self.assertEqual("", document.text_of(None))
        self.assertEqual("", document.text_of(""))

    def test_what_the_user_saw(self):
        """The exact failure: a struct must never reach the dialog as its repr."""
        text = document.text_of(FakeStruct(Year=2026, Month=12, Day=24))

        self.assertNotIn("com.sun.star", text)
        self.assertNotIn("unsigned short", text)


class ItMatchesWhatIsWrittenBack(unittest.TestCase):
    """What is read must be a value the write side accepts, or a round trip loses the field."""

    def test_every_typed_value_survives_a_round_trip(self):
        date = document.text_of(FakeStruct(Year=2026, Month=12, Day=24))
        self.assertEqual((2026, 12, 24), document.date_parts(date))

        duration = document.text_of(FakeStruct(Hours=1, Minutes=30, Seconds=0))
        self.assertEqual((1, 30, 0), document.time_parts(duration))

        self.assertIs(True, document.boolean_value(document.text_of(True)))
        self.assertEqual(4.5, document.number_value(document.text_of(4.5)))


if __name__ == "__main__":
    unittest.main()
