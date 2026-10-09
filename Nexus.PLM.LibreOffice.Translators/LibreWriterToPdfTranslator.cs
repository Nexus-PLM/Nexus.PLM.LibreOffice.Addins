using Nexus.PLM.Addin.Sdk.Translators;

namespace Nexus.PLM.LibreOffice.Translators;

/// <summary>
/// Converts an OpenDocument Text file to PDF using LibreOffice headless (the shared
/// <see cref="LibreOfficeConverter"/>: <c>LIBREOFFICE_CMD</c> first, default install path second).
/// </summary>
public sealed class LibreWriterToPdfTranslator : ITranslator
{
    /// <inheritdoc/>
    public string Key => "librewriter_to_pdf";

    /// <inheritdoc/>
    public string Label => "LibreOffice Writer → PDF";

    /// <inheritdoc/>
    public string Description =>
        "Converts an OpenDocument Text (.odt) file to PDF via LibreOffice headless. Use for archiving or distributing finalized LibreOffice Writer documents.";

    /// <inheritdoc/>
    public string InputMimeType => MimeTypes.Odt;

    /// <inheritdoc/>
    public string OutputMimeType => MimeTypes.Pdf;

    /// <inheritdoc/>
    public string OutputFileExtension => ".pdf";

    /// <inheritdoc/>
    public Task<Stream> TranslateAsync(Stream input, CancellationToken cancellationToken = default)
        => LibreOfficeConverter.ConvertToPdfAsync(input, ".odt", cancellationToken);
}
