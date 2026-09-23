"""The path/URL conversions the add-in hands to LibreOffice.

These run without an office: ``document.py`` imports no UNO at module scope, which is the whole
reason the UNO-facing calls are gathered at the bottom of that file.

    python -m unittest discover -s tests/python
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(
    os.path.dirname(__file__), "..", "..", "extension", "python", "pythonpath"))

from nexusplm import document  # noqa: E402  (the path above has to be set first)

#: The conversions are about Windows paths, and ``os.path.abspath`` is the platform's own. On a
#: Linux runner "C:\Nexus\..." is a relative name and the answers would say nothing about the
#: thing under test, so those cases report as skipped rather than as passed.
windows_only = unittest.skipUnless(os.name == "nt", "Windows paths need a Windows os.path")


@windows_only
class PathToUrl(unittest.TestCase):
    def test_the_drive_colon_is_not_encoded(self):
        """LibreOffice refuses a URL whose drive colon is percent-encoded.

        ``loadComponentFromURL("file:///C%3A/Nexus/Staging/LTD-00000001-ODT.ott")`` raises
        IllegalArgumentException — "type detection failed" — while the same file at
        ``file:///C:/...`` opens. Measured against LibreOffice 26.2; it cost a staged document that
        was created correctly and then never appeared.
        """
        url = document.path_to_url(r"C:\Nexus\Staging\LTD-00000001-ODT.ott")

        self.assertNotIn("%3A", url)
        self.assertEqual("file:///C:/Nexus/Staging/LTD-00000001-ODT.ott", url)

    def test_separators_become_forward_slashes(self):
        self.assertEqual(
            "file:///C:/Nexus/Staging/EM-1.odt",
            document.path_to_url(r"C:\Nexus\Staging\EM-1.odt"))

    def test_a_space_is_still_encoded(self):
        """Everything that is not a colon or a separator still has to be escaped."""
        self.assertEqual(
            "file:///C:/Nexus/Templates/Tracking%20Doc.ott",
            document.path_to_url(r"C:\Nexus\Templates\Tracking Doc.ott"))


@windows_only
class UrlToPath(unittest.TestCase):
    def test_it_is_the_inverse(self):
        for path in (r"C:\Nexus\Staging\EM-1.odt",
                     r"C:\Nexus\Templates\Tracking Doc.ott",
                     r"C:\Nexus\Staging\LTD-00000001-ODT.ott"):
            self.assertEqual(path, document.url_to_path(document.path_to_url(path)))

    def test_an_encoded_colon_still_reads_back(self):
        """Files staged before the fix carry the old spelling; they must still resolve."""
        self.assertEqual(
            r"C:\Nexus\Staging\EM-1.odt",
            document.url_to_path("file:///C%3A/Nexus/Staging/EM-1.odt"))

    def test_something_that_is_not_a_file_url_is_not_a_path(self):
        self.assertIsNone(document.url_to_path("private:factory/swriter"))


class Quoting(unittest.TestCase):
    """The quoting rule itself, which holds wherever the tests run."""

    def test_a_colon_survives_and_a_space_does_not(self):
        import urllib.parse

        quoted = urllib.parse.quote("C:/Nexus/Tracking Doc.ott", safe=":/")

        self.assertEqual("C:/Nexus/Tracking%20Doc.ott", quoted)


if __name__ == "__main__":
    unittest.main()
