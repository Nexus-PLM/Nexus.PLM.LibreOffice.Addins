using Nexus.PLM.Addin.Sdk.Translators;
using Nexus.PLM.Addin.Sdk.Translators.Testing;
using Nexus.PLM.LibreOffice.Translators;
using Xunit;

namespace Nexus.PLM.LibreOffice.Translators.Tests;

/// <summary>Contract tests per translator — odt_to_docx had none before the move.</summary>
public class LibreWriterToPdfContractTests : TranslatorContractTests<LibreWriterToPdfTranslator> { }

/// <summary>See <see cref="LibreWriterToPdfContractTests"/>.</summary>
public class OdtToDocxContractTests : TranslatorContractTests<OdtToDocxTranslator> { }

/// <summary>Repo-level rules across the translators.</summary>
public class LibreOfficeTranslatorSuiteTests
{
    private static readonly ITranslator[] All =
    [
        new LibreWriterToPdfTranslator(),
        new OdtToDocxTranslator(),
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
    public void CarriesTheTwoFrozenKeys() =>
        Assert.Equal(
            ["librewriter_to_pdf", "odt_to_docx"],
            All.Select(t => t.Key).OrderBy(k => k).ToArray());

    /// <summary>A missing soffice must fail with a message naming LIBREOFFICE_CMD.</summary>
    [Fact]
    public Task MissingSoffice_NamesTheEnvVar() =>
        MissingToolAssert.ThrowsNamingEnvVarAsync(new OdtToDocxTranslator(), LibreOfficeConverter.EnvironmentVariable);
}
