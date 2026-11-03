using Nexus.PLM.Addin.Sdk.Translators;
using Nexus.PLM.Addin.Sdk.Translators.Testing;
using Nexus.PLM.LibreOffice.Translators;
using Xunit;

namespace Nexus.PLM.LibreOffice.Translators.Tests;

/// <summary>Contract tests per translator — odt_to_docx had none before the move.</summary>
public class LibreWriterToPdfContractTests : TranslatorContractTests<LibreWriterToPdfTranslator> { }

/// <summary>See <see cref="LibreWriterToPdfContractTests"/>.</summary>
public class OdtToDocxContractTests : TranslatorContractTests<OdtToDocxTranslator> { }

/// <summary>See <see cref="LibreWriterToPdfContractTests"/>.</summary>
public class OdtToTxtContractTests : TranslatorContractTests<OdtToTxtTranslator> { }

/// <summary>Repo-level rules across the translators.</summary>
public class LibreOfficeTranslatorSuiteTests
{
    private static readonly ITranslator[] All =
    [
        new LibreWriterToPdfTranslator(),
        new OdtToDocxTranslator(),
        new OdtToTxtTranslator(),
    ];

    /// <summary>The server's registry is first-wins on keys AND MIME pairs.</summary>
    [Fact]
    public void KeysAndMimePairsAreUniqueWithinTheRepo()
    {
        Assert.Equal(All.Length, All.Select(t => t.Key).Distinct().Count());
        Assert.Equal(All.Length, All.Select(t => (t.InputMimeType, t.OutputMimeType)).Distinct().Count());
    }

    /// <summary>This repo owns the odt-INPUT family; docx-input conversions live in the
    /// Office repo even though both drive soffice.</summary>
    [Fact]
    public void EveryTranslatorReadsOdt() =>
        Assert.All(All, t => Assert.Equal(MimeTypes.Odt, t.InputMimeType));

    /// <summary>The frozen keys workflow nodes reference.</summary>
    [Fact]
    public void CarriesTheFrozenKeys() =>
        Assert.Equal(
            ["librewriter_to_pdf", "odt_to_docx", "odt_to_txt"],
            All.Select(t => t.Key).OrderBy(k => k).ToArray());

    /// <summary>The new translator must declare the plain-text pair and extension.</summary>
    [Fact]
    public void OdtToTxt_DeclaresPlainTextOutput()
    {
        var t = new OdtToTxtTranslator();
        Assert.Equal("text/plain", t.OutputMimeType);
        Assert.Equal(".txt", t.OutputFileExtension);
    }

    /// <summary>A missing soffice must fail with a message naming LIBREOFFICE_CMD.</summary>
    [Fact]
    public Task MissingSoffice_NamesTheEnvVar() =>
        MissingToolAssert.ThrowsNamingEnvVarAsync(new OdtToDocxTranslator(), LibreOfficeConverter.EnvironmentVariable);
}
