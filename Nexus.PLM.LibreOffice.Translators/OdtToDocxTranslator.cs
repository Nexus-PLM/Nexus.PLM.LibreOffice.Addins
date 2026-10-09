using Nexus.PLM.Addin.Sdk.Translators;

namespace Nexus.PLM.LibreOffice.Translators;

/// <summary>Converts an OpenDocument Text file to Word .docx using LibreOffice headless.</summary>
public sealed class OdtToDocxTranslator : ITranslator
{
    /// <inheritdoc/>
    public string Key => "odt_to_docx";

    /// <inheritdoc/>
    public string Label => "ODT → Word";

    /// <inheritdoc/>
    public string Description =>
        "Converts an OpenDocument Text (.odt) file to Word .docx when suppliers or customers require Microsoft Word format.";

    /// <inheritdoc/>
    public string InputMimeType => MimeTypes.Odt;

    /// <inheritdoc/>
    public string OutputMimeType => MimeTypes.Docx;

    /// <inheritdoc/>
    public string OutputFileExtension => ".docx";

    /// <inheritdoc/>
    public Task<Stream> TranslateAsync(Stream input, CancellationToken cancellationToken = default)
        => LibreOfficeConverter.ConvertAsync(input, ".odt", "docx", ".docx", cancellationToken);
}
