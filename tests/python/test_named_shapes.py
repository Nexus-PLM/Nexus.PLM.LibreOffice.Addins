"""A value you can see on a slide.

A user field is in File > Properties. In Writer it can be shown in the body as a field, and in
Calc a named range shows it in a cell — but a slide, a drawing page and a formula have nothing
that shows a user field, so Impress, Draw and Math could not DISPLAY a PLM value at all: the
add-in wrote user fields and nothing else. The server's connector (LibreOfficeTemplateConnector)
has always written a named frame or shape too; this holds that the add-in now does the same, into
the staged file before the office opens it and into the document on screen, by the same rule.

And the rule about failure: a staged file the add-in could not rewrite used to be opened in
silence, which looked exactly like a template whose fields did not match.

    python -m unittest discover -s tests/python
"""

import io
import os
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, os.path.join(ROOT, "extension", "python", "pythonpath"))

from nexusplm import document as doc  # noqa: E402
from nexusplm import odf  # noqa: E402

PRESENTATION = "application/vnd.oasis.opendocument.presentation"
PRESENTATION_TEMPLATE = "application/vnd.oasis.opendocument.presentation-template"

MANIFEST = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0">'
    '<manifest:file-entry manifest:full-path="/" manifest:media-type="%s"/>'
    '</manifest:manifest>'
)

META = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<office:document-meta xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0"><office:meta>'
    '<meta:user-defined meta:name="PartNumber"/>'
    '</office:meta></office:document-meta>'
)


def content(body):
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            '<office:body><office:presentation><draw:page draw:name="page1">'
            + body +
            '</draw:page></office:presentation></office:body></office:document-content>')


#: The shape LibreOffice writes for a frame the author named, with the author's style on its run
#: and the remainder of an older value behind it — the same fixture the server's test uses.
NAMED_FRAME = (
    '<draw:frame draw:name="NXPartNumber" svg:width="5cm"><draw:text-box>'
    '<text:p text:style-name="P1"><text:span text:style-name="Bold">old</text:span></text:p>'
    '<text:p>left over</text:p>'
    '</draw:text-box></draw:frame>'
)


def package(path, body, mime_type=PRESENTATION):
    with zipfile.ZipFile(path, "w") as out:
        stored = zipfile.ZipInfo("mimetype")
        stored.compress_type = zipfile.ZIP_STORED
        out.writestr(stored, mime_type)
        out.writestr("META-INF/manifest.xml", MANIFEST % mime_type)
        out.writestr("meta.xml", META)
        out.writestr("content.xml", content(body))
        out.writestr("styles.xml", "<office:document-styles/>")
    return path


def part(path, name):
    with zipfile.ZipFile(path) as package_:
        return package_.read(name).decode("utf-8")


class WritingShapesIntoTheStagedFile(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="nexus-shapes-")

    def path(self, name="LTD-00000009-ODP.odp"):
        return os.path.join(self.folder, name)

    def test_a_named_frame_shows_the_value(self):
        staged = package(self.path(), NAMED_FRAME)

        self.assertTrue(odf.make_document(staged, {"NXPartNumber": "EM-1"}))

        self.assertIn(">EM-1<", part(staged, "content.xml"))
        self.assertNotIn(">old<", part(staged, "content.xml"))

    def test_the_authors_formatting_survives_and_the_remainder_goes(self):
        # The same two assertions the server's WritingAShapeKeepsTheAuthorsFormatting makes, so
        # a value written by the add-in and one written by the Vault land identically.
        staged = package(self.path(), NAMED_FRAME)
        odf.make_document(staged, {"NXPartNumber": "EM-1"})

        body = part(staged, "content.xml")
        self.assertIn('<text:p text:style-name="P1"><text:span text:style-name="Bold">EM-1</text:span></text:p>', body)
        self.assertNotIn("left over", body)
        self.assertIn('svg:width="5cm"', body, "the frame itself is untouched")

    def test_a_custom_shape_is_written_too(self):
        staged = package(self.path(), (
            '<draw:custom-shape draw:name="NXRevision"><text:p>A</text:p>'
            '<draw:enhanced-geometry draw:type="rectangle"/></draw:custom-shape>'))
        odf.make_document(staged, {"NXRevision": "B"})

        body = part(staged, "content.xml")
        self.assertIn("<text:p>B</text:p>", body)
        self.assertIn('<draw:enhanced-geometry draw:type="rectangle"/>', body, "the geometry is not text")

    def test_only_a_shape_somebody_named_is_a_field(self):
        # LibreOffice writes draw:name only on a shape the author named; an untouched placeholder
        # has no name attribute at all. So a name existing is the signal.
        staged = package(self.path(), (
            '<draw:frame><draw:text-box><text:p>unnamed</text:p></draw:text-box></draw:frame>'
            + NAMED_FRAME))
        odf.make_document(staged, {"NXPartNumber": "EM-1"})

        body = part(staged, "content.xml")
        self.assertIn("<text:p>unnamed</text:p>", body)
        self.assertIn(">EM-1<", body)

    def test_a_shape_not_among_the_values_is_left_alone(self):
        staged = package(self.path(), NAMED_FRAME)
        odf.make_document(staged, {"NXRevision": "B"})
        self.assertIn(">old<", part(staged, "content.xml"))

    def test_the_name_is_matched_however_it_is_spelled(self):
        staged = package(self.path(), NAMED_FRAME)
        odf.make_document(staged, {"nxpartnumber": "EM-1"})
        self.assertIn(">EM-1<", part(staged, "content.xml"))

    def test_a_frame_with_no_paragraph_gets_one(self):
        staged = package(self.path(), '<draw:frame draw:name="NXPartNumber"><draw:text-box/></draw:frame>')
        odf.make_document(staged, {"NXPartNumber": "EM-1"})
        # A self-closing box has no body to write into; the frame is left as it is. The server
        # does the same: a box with no paragraph is given one only when the box is there.
        staged2 = package(self.path("two.odp"),
                          '<draw:frame draw:name="NXPartNumber"><draw:text-box></draw:text-box></draw:frame>')
        odf.make_document(staged2, {"NXPartNumber": "EM-1"})
        self.assertIn("<draw:text-box><text:p>EM-1</text:p></draw:text-box>", part(staged2, "content.xml"))

    def test_an_image_frame_holds_no_text_and_is_left_alone(self):
        staged = package(self.path(), '<draw:frame draw:name="NXPartNumber"><draw:image xlink:href="a.png"/></draw:frame>')
        odf.make_document(staged, {"NXPartNumber": "EM-1"})
        self.assertIn('<draw:image xlink:href="a.png"/>', part(staged, "content.xml"))
        self.assertNotIn("EM-1", part(staged, "content.xml"))

    def test_a_value_with_markup_in_it_is_escaped(self):
        staged = package(self.path(), NAMED_FRAME)
        odf.make_document(staged, {"NXPartNumber": "<b>&"})
        self.assertIn(">&lt;b&gt;&amp;<", part(staged, "content.xml"))

    def test_a_frame_inside_a_frame_does_not_confuse_the_end_of_either(self):
        # Writer nests frames; the outer one's closing tag is the second one, not the first.
        outer = ('<draw:frame draw:name="Outer"><draw:text-box>'
                 '<text:p>o</text:p>'
                 '<draw:frame draw:name="NXPartNumber"><draw:text-box><text:p>old</text:p></draw:text-box></draw:frame>'
                 '</draw:text-box></draw:frame>'
                 '<draw:frame draw:name="After"><draw:text-box><text:p>after</text:p></draw:text-box></draw:frame>')
        staged = package(self.path(), outer)
        odf.make_document(staged, {"NXPartNumber": "EM-1", "After": "done"})

        body = part(staged, "content.xml")
        self.assertIn(">EM-1<", body)
        self.assertIn(">done<", body)
        self.assertIn("<text:p>o</text:p>", body, "the outer frame's own text was not a value")

    def test_user_fields_and_shapes_are_written_together(self):
        # One rewrite, both parts: the part number is in File > Properties AND on the slide.
        staged = package(self.path(), NAMED_FRAME, PRESENTATION_TEMPLATE)
        odf.make_document(staged, {"PartNumber": "LTD-9", "NXPartNumber": "LTD-9"})

        self.assertEqual(odf.mime_type_of(staged), PRESENTATION, "and the template became a document")
        self.assertIn(">LTD-9</meta:user-defined>", part(staged, "meta.xml"))
        self.assertIn(">LTD-9<", part(staged, "content.xml"))
        self.assertEqual(part(staged, "styles.xml"), "<office:document-styles/>", "the rest survives")


class AFailedRewriteIsSaidNotSwallowed(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="nexus-shapes-")
        self.move = odf.shutil.move

    def tearDown(self):
        odf.shutil.move = self.move

    def test_it_raises_and_leaves_the_file_as_it_was(self):
        # It used to return False - the same answer as "nothing needed doing" - so the office
        # opened a file that still said "template" and nobody was told why it came up Untitled.
        staged = package(os.path.join(self.folder, "LTD-9.odp"), NAMED_FRAME, PRESENTATION_TEMPLATE)

        def refuse(*_args):
            raise OSError("the file is locked")
        odf.shutil.move = refuse

        with self.assertRaises(odf.RewriteError) as raised:
            odf.make_document(staged, {"NXPartNumber": "EM-1"})

        self.assertIn("LTD-9.odp", str(raised.exception))
        self.assertIn("locked", str(raised.exception))
        self.assertEqual(odf.mime_type_of(staged), PRESENTATION_TEMPLATE, "untouched")
        self.assertEqual([n for n in os.listdir(self.folder) if n.endswith(".tmp")], [], "no debris")

    def test_a_file_that_needs_nothing_still_answers_false_rather_than_raising(self):
        staged = package(os.path.join(self.folder, "LTD-9.odp"), NAMED_FRAME)
        self.assertFalse(odf.make_document(staged))


# ── the document on screen ───────────────────────────────────────────────────

class FakeShape:
    def __init__(self, name, text="", holds_text=True):
        self.Name = name
        self._text = text
        self._holds_text = holds_text

    def getString(self):
        if not self._holds_text:
            raise AttributeError("an image has no text")
        return self._text

    def setString(self, text):
        if not self._holds_text:
            raise AttributeError("an image has no text")
        self._text = text


class FakePage:
    def __init__(self, shapes):
        self._shapes = shapes

    def getCount(self):
        return len(self._shapes)

    def getByIndex(self, i):
        return self._shapes[i]


class FakeFrames:
    def __init__(self, frames):
        self._frames = {f.Name: f for f in frames}

    def getElementNames(self):
        return tuple(self._frames)

    def getByName(self, name):
        return self._frames[name]


class FakeDocument:
    def __init__(self, pages=None, frames=None):
        self._pages = pages
        self._frames = frames
        self.modified = False

    def getDrawPages(self):
        if self._pages is None:
            raise AttributeError("no draw pages here")
        return _Pages(self._pages)

    def getTextFrames(self):
        if self._frames is None:
            raise AttributeError("not a text document")
        return FakeFrames(self._frames)

    def setModified(self, flag):
        self.modified = flag


class _Pages:
    def __init__(self, pages):
        self._pages = [FakePage(p) for p in pages]

    def getCount(self):
        return len(self._pages)

    def getByIndex(self, i):
        return self._pages[i]


class WritingShapesOnScreen(unittest.TestCase):
    def test_a_presentations_named_shapes_are_written_on_every_slide(self):
        title = FakeShape("NXPartNumber", "old")
        rev = FakeShape("NXRevision", "A")
        unnamed = FakeShape("", "placeholder")
        deck = FakeDocument(pages=[[title, unnamed], [rev]])

        written = doc.write_fields(deck, {"NXPartNumber": "EM-1", "nxrevision": "B"})

        self.assertEqual(written, 2)
        self.assertEqual(title.getString(), "EM-1")
        self.assertEqual(rev.getString(), "B")
        self.assertEqual(unnamed.getString(), "placeholder")
        self.assertTrue(deck.modified, "so the change is saved with the document")

    def test_a_shape_that_holds_no_text_is_skipped_and_the_rest_still_written(self):
        image = FakeShape("NXPartNumber", holds_text=False)
        text = FakeShape("NXRevision", "A")
        deck = FakeDocument(pages=[[image, text]])

        self.assertEqual(doc.write_fields(deck, {"NXPartNumber": "EM-1", "NXRevision": "B"}), 1)
        self.assertEqual(text.getString(), "B")

    def test_a_text_documents_frames_are_written_too(self):
        frame = FakeShape("NXPartNumber", "old")
        writer = FakeDocument(frames=[frame])

        self.assertEqual(doc.write_fields(writer, {"NXPartNumber": "EM-1"}), 1)
        self.assertEqual(frame.getString(), "EM-1")

    def test_an_application_with_neither_contributes_nothing_and_does_not_fail(self):
        formula = FakeDocument()
        self.assertEqual(doc.write_fields(formula, {"NXPartNumber": "EM-1"}), 0)
        self.assertFalse(formula.modified)

    def test_nothing_to_write_touches_nothing(self):
        deck = FakeDocument(pages=[[FakeShape("NXPartNumber", "old")]])
        self.assertEqual(doc.write_fields(deck, {}), 0)
        self.assertFalse(deck.modified)


class ReadingShapesOnScreen(unittest.TestCase):
    def test_edit_values_starts_from_what_the_slide_shows(self):
        deck = FakeDocument(pages=[[FakeShape("NXPartNumber", "EM-1"), FakeShape("", "placeholder"),
                                    FakeShape("Logo", holds_text=False)]])
        self.assertEqual(doc.fields(deck), {"NXPartNumber": "EM-1"})

    def test_a_user_field_wins_over_a_shape_of_the_same_name(self):
        # As the server's reader decides it: the property is the one every application carries.
        class WithProperties(FakeDocument):
            def getDocumentProperties(self):
                outer = self

                class Props:
                    def getUserDefinedProperties(self):
                        class Container:
                            def getPropertySetInfo(self):
                                class Info:
                                    def getProperties(self):
                                        class P:
                                            Name = "NXPartNumber"
                                        return [P()]
                                return Info()

                            def getPropertyValue(self, _name):
                                return "from-properties"
                        return Container()
                return Props()

        deck = WithProperties(pages=[[FakeShape("NXPartNumber", "from-the-slide")]])
        self.assertEqual(doc.fields(deck)["NXPartNumber"], "from-properties")


# ── the command that opens a staged file ─────────────────────────────────────

def _read(*parts):
    with io.open(os.path.join(ROOT, *parts), encoding="utf-8") as handle:
        return handle.read()


class TheCommandsWriteEveryField(unittest.TestCase):
    """nexus_commands.py imports UNO at call time and cannot be run here, so its text is held."""

    def setUp(self):
        self.source = _read("extension", "python", "nexus_commands.py")

    def test_every_write_goes_through_write_fields(self):
        # A command writing user fields alone is a command whose value never reaches a slide.
        self.assertNotIn("write_user_fields(", self.source)
        self.assertGreaterEqual(self.source.count("doc.write_fields("), 5)

    def test_edit_values_and_save_as_start_from_every_field(self):
        self.assertNotIn("doc.user_fields(", self.source)
        self.assertGreaterEqual(self.source.count("doc.fields(document)"), 2)

    def test_a_staged_file_that_could_not_be_rewritten_is_said_and_still_opened(self):
        start = self.source.index("def _open_with_values(")
        end = self.source.index("\n@_command", start)
        body = self.source[start:end]

        self.assertIn("except odf.RewriteError", body)
        self.assertIn("_say(client,", body[body.index("except odf.RewriteError"):])
        self.assertIn("prepare=False", body, "opened as it was staged, rather than not at all")
        self.assertIn("_log(", body[body.index("except odf.RewriteError"):])


if __name__ == "__main__":
    unittest.main()
