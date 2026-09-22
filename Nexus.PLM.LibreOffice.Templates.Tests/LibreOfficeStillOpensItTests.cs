using System.Diagnostics;
using FluentAssertions;
using Xunit;

namespace Nexus.PLM.LibreOffice.Templates.Tests;

/// <summary>
/// The end-to-end question the unit tests cannot answer: after this connector rewrites a file,
/// does <b>LibreOffice</b> still open it, and does it see the values that were written?
/// <para>
/// Worth its own class because a package can be wrong in ways nothing else here would notice: it
/// passes every zip tool, parses as XML, and round-trips through this connector perfectly, and
/// LibreOffice is the only thing that can say whether it is really a document.
/// </para>
/// <para>
/// What this test is <b>not</b>: a guard on the <c>mimetype</c> rule. That was checked by breaking
/// it on purpose, and LibreOffice 26.2 opened the file anyway — so the claim that it would refuse
/// was wrong, and the assertion that our output keeps <c>mimetype</c> first and stored lives in
/// <c>LibreOfficeTemplateConnectorTests</c> where it is deterministic. What this test does catch is
/// a package LibreOffice genuinely cannot read, and whether the values written are the values it
/// then sees.
/// </para>
/// <para>
/// Skipped where LibreOffice is not installed, so CI stays green. That makes it a test that only
/// ever runs on a machine that can actually answer it, which is the point.
/// </para>
/// </summary>
public class LibreOfficeStillOpensItTests : IDisposable
{
    private readonly string _dir =
        Path.Combine(Path.GetTempPath(), "nexus-odf-" + Guid.NewGuid().ToString("N")[..8]);

    public LibreOfficeStillOpensItTests() => Directory.CreateDirectory(_dir);

    public void Dispose()
    {
        try { if (Directory.Exists(_dir)) Directory.Delete(_dir, recursive: true); } catch { /* best effort */ }
        GC.SuppressFinalize(this);
    }

    /// <summary>Where LibreOffice is, or <see langword="null"/> when it is not installed.</summary>
    private static string? SofficePath => new[]
    {
        @"C:\Program Files\LibreOffice\program\soffice.exe",
        @"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/usr/local/bin/soffice",
    }.FirstOrDefault(File.Exists);

    private static bool Convert(string soffice, string input, string outDir, string filter)
    {
        using var process = Process.Start(new ProcessStartInfo(soffice)
        {
            ArgumentList = { "--headless", "--convert-to", filter, "--outdir", outDir, input },
            RedirectStandardOutput = true,
            RedirectStandardError  = true,
            UseShellExecute        = false,
        })!;

        return process.WaitForExit(milliseconds: 300_000) && process.ExitCode == 0;
    }

    /// <summary>
    /// A document LibreOffice itself produced, carrying user fields of each type. Built from flat
    /// ODF so the fixture is readable here, then converted by LibreOffice so the package under test
    /// is genuinely one of its own rather than one of ours.
    /// </summary>
    private string SeedWrittenByLibreOffice(string soffice)
    {
        var flat = Path.Combine(_dir, "seed.fodt");
        File.WriteAllText(flat,
            """<?xml version="1.0" encoding="UTF-8"?>""" +
            """<office:document xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" """ +
            """xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" """ +
            """xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" """ +
            """office:version="1.3" office:mimetype="application/vnd.oasis.opendocument.text">""" +
            """<office:meta>""" +
            """<meta:user-defined meta:name="PartNumber">SEED-1</meta:user-defined>""" +
            """<meta:user-defined meta:name="Qty" meta:value-type="float">7</meta:user-defined>""" +
            """<meta:user-defined meta:name="ModifiedDate" meta:value-type="date">2020-01-01T00:00:00</meta:user-defined>""" +
            """</office:meta>""" +
            """<office:body><office:text><text:p>Body text</text:p></office:text></office:body>""" +
            """</office:document>""");

        Convert(soffice, flat, _dir, "odt").Should().BeTrue("LibreOffice must be able to write the seed");

        var seed = Path.Combine(_dir, "seed.odt");
        File.Exists(seed).Should().BeTrue();
        return seed;
    }

    /// <summary>
    /// Reported as <b>skipped</b>, never as passed, where LibreOffice is absent. A test that
    /// quietly returns and goes green is worse than no test: it is a green tick claiming an
    /// assurance nobody actually has.
    /// </summary>
    [SkippableFact]
    public void AFileThisConnectorWrote_StillOpensInLibreOffice()
    {
        var soffice = SofficePath;
        Skip.If(soffice is null, "LibreOffice is not installed, so only it can answer this and it is not here.");

        var seed = SeedWrittenByLibreOffice(soffice);
        var written = Path.Combine(_dir, "written.odt");

        using (var input  = File.OpenRead(seed))
        using (var output = File.Create(written))
        {
            new LibreOfficeTemplateConnector().WriteValues(input, output, new Dictionary<string, string>
            {
                ["PartNumber"]   = "EM-00000039-DOC",
                ["ModifiedDate"] = "2026-09-20",
                ["Qty"]          = "",            // typed and empty: must be left alone
            });
        }

        // The whole point: LibreOffice's own verdict on the package we produced.
        var verifyDir = Path.Combine(_dir, "verify");
        Directory.CreateDirectory(verifyDir);
        Convert(soffice, written, verifyDir, "txt:Text").Should().BeTrue(
            "LibreOffice must still be able to open the rewritten package");

        var text = Path.Combine(verifyDir, "written.txt");
        File.Exists(text).Should().BeTrue();
        File.ReadAllText(text).Should().Contain("Body text", "the document's content must survive");

        // And it still holds what was written, read back through the connector.
        using var reread = File.OpenRead(written);
        var values = new LibreOfficeTemplateConnector().ReadValues(reread);

        values["PartNumber"].Should().Be("EM-00000039-DOC");
        values["ModifiedDate"].Should().Be("2026-09-20T00:00:00");
        values["Qty"].Should().Be("7", "an empty value cannot be a number, so the seed's value stands");
    }
}
