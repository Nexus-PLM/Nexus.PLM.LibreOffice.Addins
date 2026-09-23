"""A staged template body, made into the document it is named as.

New from Template stages a copy of the type's template. The copy is named for the new part number
— LTD-00000005-ODT.odt — but its body still says
``application/vnd.oasis.opendocument.text-template``, and LibreOffice detects a document by its
body. So it did what a template is for: opened a new "Untitled 1" from it and left the staged file
alone, with the values PLM sent going into the untitled copy and Check In having nothing to upload.

Naming the staged file correctly (AddinService #357) was half of it; this is the other half.
"""

import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), "..", "..", "extension", "python", "pythonpath"))

from nexusplm import odf  # noqa: E402

META = (
    """<?xml version="1.0" encoding="UTF-8"?>"""
    """<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" """
    """xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0"><office:meta>"""
    """<meta:user-defined meta:name="PartNumber">LTD-00000005-ODT</meta:user-defined>"""
    """</office:meta></office:document-meta>"""
)


MANIFEST = (
    """<?xml version="1.0" encoding="UTF-8"?>"""
    """<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" """
    """manifest:version="1.4">"""
    """<manifest:file-entry manifest:full-path="/" manifest:version="1.4" """
    """manifest:media-type="%s"/>"""
    """<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>"""
    """</manifest:manifest>"""
)


def package(path, mime_type, extra=("meta.xml", META)):
    with zipfile.ZipFile(path, "w") as out:
        stored = zipfile.ZipInfo("mimetype")
        stored.compress_type = zipfile.ZIP_STORED
        out.writestr(stored, mime_type)
        out.writestr("META-INF/manifest.xml", MANIFEST % mime_type)
        out.writestr(extra[0], extra[1])
        out.writestr("content.xml", "<office:document-content/>")
    return path


class MakingADocumentOfIt(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="nexus-odf-")

    def path(self, name):
        return os.path.join(self.folder, name)

    def test_a_template_body_named_as_a_document(self):
        staged = package(self.path("LTD-00000005-ODT.odt"),
                         "application/vnd.oasis.opendocument.text-template")

        self.assertTrue(odf.make_document(staged))

        self.assertEqual("application/vnd.oasis.opendocument.text", odf.mime_type_of(staged))

    def test_every_application(self):
        for extension, template, document in (
            (".odt", "text-template", "text"),
            (".ods", "spreadsheet-template", "spreadsheet"),
            (".odp", "presentation-template", "presentation"),
            (".odg", "graphics-template", "graphics"),
            (".odf", "formula-template", "formula"),
        ):
            staged = package(self.path("LTD-1" + extension),
                             "application/vnd.oasis.opendocument." + template)

            self.assertTrue(odf.make_document(staged), extension)
            self.assertEqual("application/vnd.oasis.opendocument." + document,
                             odf.mime_type_of(staged), extension)

    def test_the_rest_of_the_package_survives(self):
        """The body is the user's document: only the one line that names its type may change."""
        staged = package(self.path("LTD-1.odt"), "application/vnd.oasis.opendocument.text-template")

        odf.make_document(staged)

        with zipfile.ZipFile(staged) as after:
            self.assertEqual(["mimetype", "META-INF/manifest.xml", "meta.xml", "content.xml"],
                             after.namelist())
            self.assertIn("LTD-00000005-ODT", after.read("meta.xml").decode())

    def test_mimetype_stays_first_and_uncompressed(self):
        """What ODF requires of every package, and what a rewrite is most likely to break."""
        staged = package(self.path("LTD-1.odt"), "application/vnd.oasis.opendocument.text-template")

        odf.make_document(staged)

        with zipfile.ZipFile(staged) as after:
            first = after.infolist()[0]
            self.assertEqual("mimetype", first.filename)
            self.assertEqual(zipfile.ZIP_STORED, first.compress_type)

    def test_a_document_is_left_alone(self):
        staged = package(self.path("LTD-1.odt"), "application/vnd.oasis.opendocument.text")

        self.assertFalse(odf.make_document(staged))
        self.assertEqual("application/vnd.oasis.opendocument.text", odf.mime_type_of(staged))

    def test_a_file_named_as_a_template_is_left_alone(self):
        """Someone opening a real template means to use it as one."""
        staged = package(self.path("Tracking.ott"), "application/vnd.oasis.opendocument.text-template")

        self.assertFalse(odf.make_document(staged))
        self.assertEqual("application/vnd.oasis.opendocument.text-template", odf.mime_type_of(staged))

    def test_something_that_is_not_an_opendocument_package(self):
        other = self.path("drawing.odg")
        with open(other, "wb") as handle:
            handle.write(b"not a zip at all")

        self.assertFalse(odf.make_document(other))
        self.assertIsNone(odf.mime_type_of(other))
        with open(other, "rb") as handle:
            self.assertEqual(b"not a zip at all", handle.read(), "it must be left untouched")

    def test_the_manifest_agrees_with_the_mimetype(self):
        """The half that was missed: a package whose two type declarations disagree opens with
        "(repaired document)" across the title bar, because by ODF they have to say the same."""
        staged = package(self.path("LTD-1.odt"), "application/vnd.oasis.opendocument.text-template")

        odf.make_document(staged)

        with zipfile.ZipFile(staged) as after:
            manifest = after.read("META-INF/manifest.xml").decode()

        self.assertIn('manifest:full-path="/" manifest:version="1.4" '
                      'manifest:media-type="application/vnd.oasis.opendocument.text"', manifest)
        self.assertNotIn("text-template", manifest)

    def test_only_the_root_entry_of_the_manifest_changes(self):
        """Every other entry names a part, not the document; rewriting one would lose a part."""
        staged = package(self.path("LTD-1.odt"), "application/vnd.oasis.opendocument.text-template")

        odf.make_document(staged)

        with zipfile.ZipFile(staged) as after:
            manifest = after.read("META-INF/manifest.xml").decode()

        self.assertIn('manifest:full-path="content.xml" manifest:media-type="text/xml"', manifest)

    def test_a_package_with_no_manifest(self):
        """Not every ODF package carries one, and a missing manifest is not a reason to give up."""
        staged = self.path("LTD-1.odt")
        with zipfile.ZipFile(staged, "w") as out:
            stored = zipfile.ZipInfo("mimetype")
            stored.compress_type = zipfile.ZIP_STORED
            out.writestr(stored, "application/vnd.oasis.opendocument.text-template")
            out.writestr("content.xml", "<office:document-content/>")

        self.assertTrue(odf.make_document(staged))
        self.assertEqual("application/vnd.oasis.opendocument.text", odf.mime_type_of(staged))

    def test_a_file_that_is_not_there(self):
        self.assertFalse(odf.make_document(self.path("gone.odt")))


if __name__ == "__main__":
    unittest.main()
