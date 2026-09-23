"""PLM's values, written into the staged file before anything opens it.

They used to be written into the document once it was open, which works only for as long as
nothing asks the file itself what it holds — and Check In, a backup, and a colleague opening the
staged path all do. This repo's own rule says the file is written first; it was the one rule
inherited from the Office add-ins that this add-in did not keep.

The lexical forms are OdfValueWrite's, so a value written here and a value written by the server
are the same value.
"""

import os
import re
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), "..", "..", "extension", "python", "pythonpath"))

from nexusplm import odf  # noqa: E402

FIELDS = (
    ("PartNumber", "string", ""),
    ("Revision", "string", ""),
    ("CreationDate", "date", "2026-01-01T00:00:00"),
    ("Approved", "boolean", "false"),
    ("Priority", "float", "3"),
    ("Author", None, ""),
)

MANIFEST = (
    """<?xml version="1.0" encoding="UTF-8"?>"""
    """<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">"""
    """<manifest:file-entry manifest:full-path="/" manifest:media-type="%s"/>"""
    """</manifest:manifest>"""
)


def meta():
    body = "".join(
        '<meta:user-defined meta:name="%s"%s>%s</meta:user-defined>'
        % (name, '' if kind is None else ' meta:value-type="%s"' % kind, value)
        for name, kind, value in FIELDS)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0">'
            '<office:meta>' + body + '</office:meta></office:document-meta>')


def package(path, mime_type="application/vnd.oasis.opendocument.text"):
    with zipfile.ZipFile(path, "w") as out:
        stored = zipfile.ZipInfo("mimetype")
        stored.compress_type = zipfile.ZIP_STORED
        out.writestr(stored, mime_type)
        out.writestr("META-INF/manifest.xml", MANIFEST % mime_type)
        out.writestr("meta.xml", meta())
        out.writestr("content.xml", "<office:document-content/>")
    return path


def values_of(path):
    with zipfile.ZipFile(path) as package_:
        text = package_.read("meta.xml").decode()
    return dict(re.findall(r'<meta:user-defined meta:name="(\w+)"[^>]*>([^<]*)<', text))


class WritingTheStagedFile(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="nexus-staged-")

    def path(self, name="LTD-00000007-ODT.odt"):
        return os.path.join(self.folder, name)

    def test_the_values_are_in_the_file_before_anybody_opens_it(self):
        staged = package(self.path())

        self.assertTrue(odf.make_document(staged, {
            "PartNumber": "LTD-00000007-ODT",
            "Revision": "B",
            "Author": "Marc Jeeves",
        }))

        after = values_of(staged)
        self.assertEqual("LTD-00000007-ODT", after["PartNumber"])
        self.assertEqual("B", after["Revision"])
        self.assertEqual("Marc Jeeves", after["Author"])

    def test_each_typed_field_keeps_its_type(self):
        """The forms OdfValueWrite writes, so open and closed give the same value."""
        staged = package(self.path())

        odf.make_document(staged, {
            "CreationDate": "2026-09-22",
            "Approved": "yes",
            "Priority": "4.5",
        })

        after = values_of(staged)
        self.assertEqual("2026-09-22T00:00:00", after["CreationDate"])
        self.assertEqual("true", after["Approved"])
        self.assertEqual("4.5", after["Priority"])

    def test_a_whole_number_is_not_written_with_a_decimal_point(self):
        staged = package(self.path())

        odf.make_document(staged, {"Priority": "7"})

        self.assertEqual("7", values_of(staged)["Priority"])

    def test_a_value_the_type_cannot_hold_leaves_the_field_alone(self):
        staged = package(self.path())

        odf.make_document(staged, {"CreationDate": "next Tuesday", "Priority": "high"})

        after = values_of(staged)
        self.assertEqual("2026-01-01T00:00:00", after["CreationDate"])
        self.assertEqual("3", after["Priority"])

    def test_an_empty_value_does_not_blank_a_typed_field(self):
        """The template author's value stands; an empty value is not a date or a number."""
        staged = package(self.path())

        odf.make_document(staged, {"CreationDate": "", "Priority": "", "Approved": ""})

        after = values_of(staged)
        self.assertEqual("2026-01-01T00:00:00", after["CreationDate"])
        self.assertEqual("3", after["Priority"])
        self.assertEqual("false", after["Approved"])

    def test_an_empty_string_does_clear_a_string(self):
        staged = package(self.path())
        odf.make_document(staged, {"Author": "Marc"})

        odf.make_document(staged, {"Author": ""})

        self.assertEqual("", values_of(staged)["Author"])

    def test_a_field_the_document_does_not_have_is_not_invented(self):
        staged = package(self.path())

        odf.make_document(staged, {"NotInHere": "should not appear"})

        with zipfile.ZipFile(staged) as after:
            self.assertNotIn("NotInHere", after.read("meta.xml").decode())

    def test_the_name_is_matched_however_it_is_spelled(self):
        staged = package(self.path())

        odf.make_document(staged, {"partnumber": "LTD-1"})

        self.assertEqual("LTD-1", values_of(staged)["PartNumber"])

    def test_a_value_with_markup_in_it_is_escaped(self):
        staged = package(self.path())

        odf.make_document(staged, {"Author": 'Marc & <b>Co</b>'})

        self.assertEqual("Marc & <b>Co</b>", values_of(staged)["Author"].replace("&amp;", "&")
                         .replace("&lt;", "<").replace("&gt;", ">"))
        with zipfile.ZipFile(staged) as after:
            after.read("meta.xml").decode()   # still readable

    def test_writing_values_and_making_a_document_happen_together(self):
        """One rewrite does both: a staged template body, filled in."""
        staged = package(self.path(), "application/vnd.oasis.opendocument.text-template")

        self.assertTrue(odf.make_document(staged, {"PartNumber": "LTD-00000007-ODT"}))

        self.assertEqual("application/vnd.oasis.opendocument.text", odf.mime_type_of(staged))
        self.assertEqual("LTD-00000007-ODT", values_of(staged)["PartNumber"])

    def test_a_file_that_needs_neither_is_left_alone(self):
        staged = package(self.path())
        with open(staged, "rb") as handle:
            before = handle.read()

        self.assertFalse(odf.make_document(staged))

        with open(staged, "rb") as handle:
            self.assertEqual(before, handle.read())

    def test_the_rest_of_the_package_survives(self):
        staged = package(self.path())

        odf.make_document(staged, {"PartNumber": "LTD-1"})

        with zipfile.ZipFile(staged) as after:
            self.assertEqual(["mimetype", "META-INF/manifest.xml", "meta.xml", "content.xml"],
                             after.namelist())
            self.assertEqual(zipfile.ZIP_STORED, after.infolist()[0].compress_type)


if __name__ == "__main__":
    unittest.main()


class AFieldWithNoValueYet(unittest.TestCase):
    """The fields PLM fills in are exactly the ones a template leaves empty.

    LibreOffice writes an empty property self-closing — ``<meta:user-defined meta:name="Author"/>``
    — and a pattern that only knew the ``<x>value</x>`` shape skipped every one of them. Live, that
    meant a staged document with its dates and its number written in and no part number.
    """

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="nexus-empty-")

    def package_with_empty_fields(self):
        path = os.path.join(self.folder, "LTD-00000008-ODT.odt")
        meta_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0"><office:meta>'
            '<meta:user-defined meta:name="PartNumber" meta:value-type="string"/>'
            '<meta:user-defined meta:name="Author"/>'
            '<meta:user-defined meta:name="Priority" meta:value-type="float">3</meta:user-defined>'
            '</office:meta></office:document-meta>')
        with zipfile.ZipFile(path, "w") as out:
            stored = zipfile.ZipInfo("mimetype")
            stored.compress_type = zipfile.ZIP_STORED
            out.writestr(stored, "application/vnd.oasis.opendocument.text")
            out.writestr("meta.xml", meta_xml)
        return path

    def test_an_empty_field_is_written(self):
        staged = self.package_with_empty_fields()

        odf.make_document(staged, {"PartNumber": "LTD-00000008-ODT", "Author": "Marc Jeeves"})

        after = values_of(staged)
        self.assertEqual("LTD-00000008-ODT", after["PartNumber"])
        self.assertEqual("Marc Jeeves", after["Author"])

    def test_it_keeps_the_type_the_field_was_given(self):
        staged = self.package_with_empty_fields()

        odf.make_document(staged, {"PartNumber": "LTD-1"})

        with zipfile.ZipFile(staged) as after:
            text = after.read("meta.xml").decode()
        self.assertIn('meta:name="PartNumber" meta:value-type="string">LTD-1', text)

    def test_a_field_with_a_value_still_works(self):
        staged = self.package_with_empty_fields()

        odf.make_document(staged, {"Priority": "9"})

        self.assertEqual("9", values_of(staged)["Priority"])
