using FluentAssertions;
using Nexus.PLM.Addin.Sdk.Templates;

namespace Nexus.PLM.LibreOffice.Templates.Tests;

/// <summary>
/// The connector, over real OpenDocument packages: what fields a document has, what they currently
/// hold, and what it looks like after PLM's values go in.
/// </summary>
public class LibreOfficeTemplateConnectorTests
{
    private static readonly LibreOfficeTemplateConnector Connector = new();

    private static IReadOnlyDictionary<string, string> WriteThenRead(
        Stream template, IDictionary<string, string> values)
    {
        using var output = new MemoryStream();
        template.Position = 0;
        Connector.WriteValues(template, output, new Dictionary<string, string>(values));

        output.Position = 0;
        return Connector.ReadValues(output);
    }

    // ── What it says it is ───────────────────────────────────────────────────

    [Fact]
    public void ItAnswersToOneAppKeyForAllFiveApplications()
        => Connector.AppKey.Should().Be("libreoffice");

    /// <summary>
    /// Every application, and — the part the Office add-ins still get wrong — every application's
    /// template type too. A missing template MIME row means a PLM type cannot be given a template
    /// at all, which is why `.potx` and `.xltx` are still outstanding over there.
    /// </summary>
    [Theory]
    [InlineData(OdfMimeTypes.Text, ".odt")]
    [InlineData(OdfMimeTypes.TextTemplate, ".ott")]
    [InlineData(OdfMimeTypes.Spreadsheet, ".ods")]
    [InlineData(OdfMimeTypes.SpreadsheetTemplate, ".ots")]
    [InlineData(OdfMimeTypes.Presentation, ".odp")]
    [InlineData(OdfMimeTypes.PresentationTemplate, ".otp")]
    [InlineData(OdfMimeTypes.Graphics, ".odg")]
    [InlineData(OdfMimeTypes.GraphicsTemplate, ".otg")]
    [InlineData(OdfMimeTypes.Formula, ".odf")]
    [InlineData(OdfMimeTypes.FormulaTemplate, ".otf")]
    public void EveryApplicationAndItsTemplateTypeIsSupported(string mimeType, string extension)
    {
        Connector.SupportedMimeTypes.Should().Contain(mimeType);
        OdfMimeTypes.IsSupported(mimeType).Should().BeTrue();
        OdfMimeTypes.ExtensionFor(mimeType).Should().Be(extension);
    }

    [Fact]
    public void TheExtensionListIsWhatAHostDeclares()
        => OdfMimeTypes.ExtensionList.Should().Be(".odt;.ott;.ods;.ots;.odp;.otp;.odg;.otg;.odf;.otf");

    [Fact]
    public void SomethingThatIsNotOpenDocument_IsNotSupported()
    {
        OdfMimeTypes.IsSupported("application/vnd.openxmlformats-officedocument.wordprocessingml.document")
            .Should().BeFalse();
        OdfMimeTypes.ExtensionFor(null).Should().BeNull();
    }

    // ── Inspecting ──────────────────────────────────────────────────────────

    [Fact]
    public void TheUserFieldsOfADocumentAreItsFields()
    {
        using var doc = OdfDocument.Writer(
            OdfDocument.UserField("PartNumber", "SEED-1"),
            OdfDocument.UserField("Revision", "A", "string"),
            OdfDocument.UserField("ModifiedDate", "2026-01-02T03:04:05", "date"));

        Connector.GetFields(doc).Should().BeEquivalentTo(new[]
        {
            new TemplateField("PartNumber",   FieldKinds.UserField),
            new TemplateField("Revision",     FieldKinds.UserField),
            new TemplateField("ModifiedDate", FieldKinds.UserField),
        });
    }

    [Fact]
    public void ADocumentWithNoFields_HasNone()
    {
        using var doc = OdfDocument.Writer();
        Connector.GetFields(doc).Should().BeEmpty();
    }

    [Fact]
    public void ACalcNamedRange_IsAField()
    {
        using var doc = OdfDocument.Package(OdfMimeTypes.Spreadsheet,
            contentBody: """<office:spreadsheet><table:named-expressions>""" +
                         """<table:named-range table:name="NXPartNumber" table:cell-range-address="Sheet1.A1"/>""" +
                         """</table:named-expressions></office:spreadsheet>""");

        Connector.GetFields(doc).Should().ContainEquivalentOf(
            new TemplateField("NXPartNumber", FieldKinds.NamedRange));
    }

    /// <summary>
    /// The measured difference from PowerPoint, and the reason this connector needs no heuristic:
    /// LibreOffice stores a <c>draw:name</c> only on a shape somebody deliberately named. An
    /// untouched placeholder or a freshly drawn box has no name attribute at all, so "has a name"
    /// IS the signal. PowerPoint invents a name for everything, and telling its real fields from
    /// its "Title Placeholder 1"s took two wrong guesses and a real template to settle.
    /// </summary>
    [Fact]
    public void OnlyAShapeSomebodyNamed_IsAField()
    {
        using var doc = OdfDocument.Package(OdfMimeTypes.Presentation,
            contentBody: """<office:presentation><draw:page draw:name="page1">""" +
                         """<draw:frame draw:name="NXPartNumber"><draw:text-box>""" +
                         """<text:p>placeholder</text:p></draw:text-box></draw:frame>""" +
                         """<draw:frame><draw:text-box><text:p>unnamed</text:p></draw:text-box></draw:frame>""" +
                         """</draw:page></office:presentation>""");

        Connector.GetFields(doc).Should().BeEquivalentTo(new[]
        {
            new TemplateField("NXPartNumber", FieldKinds.NamedShape),
        });
    }

    // ── Reading ─────────────────────────────────────────────────────────────

    [Fact]
    public void ReadingGivesTheCurrentValues()
    {
        using var doc = OdfDocument.Writer(
            OdfDocument.UserField("PartNumber", "SEED-1"),
            OdfDocument.UserField("Qty", "7", "float"));

        Connector.ReadValues(doc).Should().BeEquivalentTo(new Dictionary<string, string>
        {
            ["PartNumber"] = "SEED-1",
            ["Qty"]        = "7",
        });
    }

    [Fact]
    public void ReadingCanBeNarrowedToTheFieldsWanted()
    {
        using var doc = OdfDocument.Writer(
            OdfDocument.UserField("PartNumber", "SEED-1"),
            OdfDocument.UserField("Revision", "A"));

        // Case-insensitively, as the SDK contract specifies.
        Connector.ReadValues(doc, new[] { "partnumber" }).Should().BeEquivalentTo(
            new Dictionary<string, string> { ["PartNumber"] = "SEED-1" });
    }

    // ── Writing ─────────────────────────────────────────────────────────────

    [Fact]
    public void WritingFillsTheFieldsTheDocumentHas()
    {
        using var doc = OdfDocument.Writer(
            OdfDocument.UserField("PartNumber", "SEED-1"),
            OdfDocument.UserField("Revision", "A"));

        WriteThenRead(doc, new Dictionary<string, string>
        {
            ["PartNumber"] = "EM-00000039-DOC",
            ["Revision"]   = "C",
        }).Should().BeEquivalentTo(new Dictionary<string, string>
        {
            ["PartNumber"] = "EM-00000039-DOC",
            ["Revision"]   = "C",
        });
    }

    /// <summary>
    /// A field nobody put in the template is not a field of it. Inventing one would make the file
    /// claim a field it does not really have, and the data modeller would then offer it.
    /// </summary>
    [Fact]
    public void AFieldTheTemplateDoesNotHave_IsNotInvented()
    {
        using var doc = OdfDocument.Writer(OdfDocument.UserField("PartNumber", "SEED-1"));

        var after = WriteThenRead(doc, new Dictionary<string, string>
        {
            ["PartNumber"]  = "EM-1",
            ["NotInHere"]   = "should not appear",
        });

        after.Should().ContainKey("PartNumber");
        after.Should().NotContainKey("NotInHere");
    }

    [Fact]
    public void ATypedFieldKeepsItsType_AndAnEmptyValueLeavesItAlone()
    {
        using var doc = OdfDocument.Writer(
            OdfDocument.UserField("ModifiedDate", "2020-01-01T00:00:00", "date"),
            OdfDocument.UserField("Qty", "7", "float"));

        using var output = new MemoryStream();
        doc.Position = 0;
        Connector.WriteValues(doc, output, new Dictionary<string, string>
        {
            ["ModifiedDate"] = "2026-09-20",
            ["Qty"]          = "",
        });

        var meta = OdfDocument.PartOf(output, "meta.xml");
        meta.Should().Contain("""meta:name="ModifiedDate" meta:value-type="date">2026-09-20T00:00:00""");
        meta.Should().Contain("""meta:name="Qty" meta:value-type="float">7""",
            "an empty value cannot be a number, so the template's own value stands");
    }

    [Fact]
    public void WritingAShapeKeepsTheAuthorsFormatting()
    {
        using var doc = OdfDocument.Package(OdfMimeTypes.Presentation,
            contentBody: """<office:presentation><draw:page draw:name="page1">""" +
                         """<draw:frame draw:name="NXPartNumber"><draw:text-box>""" +
                         """<text:p><text:span text:style-name="Bold">old</text:span></text:p>""" +
                         """<text:p>left over</text:p>""" +
                         """</draw:text-box></draw:frame></draw:page></office:presentation>""");

        using var output = new MemoryStream();
        doc.Position = 0;
        Connector.WriteValues(doc, output, new Dictionary<string, string> { ["NXPartNumber"] = "EM-1" });

        var content = OdfDocument.PartOf(output, "content.xml");
        content.Should().Contain("""<text:span text:style-name="Bold">EM-1</text:span>""",
            "the author chose that style for the frame; a fresh run would discard it");
        content.Should().NotContain("left over", "the second paragraph was the old value's remainder");
    }

    // ── The package itself ──────────────────────────────────────────────────

    /// <summary>
    /// The rule that produces a file which passes every zip tool and which LibreOffice then refuses:
    /// <c>mimetype</c> must be the first entry and stored uncompressed.
    /// </summary>
    [Fact]
    public void TheRewrittenPackageKeepsMimetypeFirstAndUncompressed()
    {
        using var doc = OdfDocument.Writer(OdfDocument.UserField("PartNumber", "SEED-1"));

        using var output = new MemoryStream();
        doc.Position = 0;
        Connector.WriteValues(doc, output, new Dictionary<string, string> { ["PartNumber"] = "EM-1" });

        OdfDocument.EntryNames(output).First().Should().Be("mimetype");
        OdfDocument.IsStored(output, "mimetype").Should().BeTrue();
        OdfDocument.PartOf(output, "mimetype").Should().Be(OdfMimeTypes.Text);
    }

    [Fact]
    public void EveryOtherPartSurvivesUntouched()
    {
        using var doc = OdfDocument.Package(OdfMimeTypes.Text,
            metaBody: OdfDocument.UserField("PartNumber", "SEED-1"),
            contentBody: """<office:text><text:p>Body text nobody asked us to change</text:p></office:text>""");

        using var output = new MemoryStream();
        doc.Position = 0;
        Connector.WriteValues(doc, output, new Dictionary<string, string> { ["PartNumber"] = "EM-1" });

        OdfDocument.EntryNames(output).Should().BeEquivalentTo(new[] { "mimetype", "meta.xml", "content.xml" });
        OdfDocument.PartOf(output, "content.xml").Should().Contain("Body text nobody asked us to change");
    }

    [Fact]
    public void WritingNothingStillProducesAValidPackage()
    {
        using var doc = OdfDocument.Writer(OdfDocument.UserField("PartNumber", "SEED-1"));

        using var output = new MemoryStream();
        doc.Position = 0;
        Connector.WriteValues(doc, output, new Dictionary<string, string>());

        Connector.ReadValues(output).Should().BeEquivalentTo(
            new Dictionary<string, string> { ["PartNumber"] = "SEED-1" });
    }

    [Fact]
    public void AStreamIsNeverOptional()
    {
        Assert.Throws<ArgumentNullException>(() => Connector.GetFields(null!));
        Assert.Throws<ArgumentNullException>(() => Connector.ReadValues(null!));
        using var doc = OdfDocument.Writer();
        Assert.Throws<ArgumentNullException>(() => Connector.WriteValues(doc, null!, new Dictionary<string, string>()));
    }
}
