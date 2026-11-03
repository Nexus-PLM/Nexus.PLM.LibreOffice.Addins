using Nexus.PLM.Addin.Sdk.Translators;

namespace Nexus.PLM.LibreOffice.Translators;

/// <summary>Converts an OpenDocument Text file to plain text using LibreOffice headless.</summary>
public sealed class OdtToTxtTranslator : ITranslator
{
    /// <summary>The soffice <c>--convert-to</c> filter for plain text output.</summary>
    private const string TextFilter = "txt:Text";

    /// <inheritdoc/>
    public string Key => "odt_to_txt";

    /// <inheritdoc/>
    public string Label => "ODT → Text";

    /// <inheritdoc/>
    public string Description =>
        "Extracts the text of an OpenDocument Text (.odt) file as plain text for indexing, diffing or lightweight preview.";

    /// <inheritdoc/>
    public string InputMimeType => MimeTypes.Odt;

    /// <inheritdoc/>
    public string OutputMimeType => MimeTypes.Txt;

    /// <inheritdoc/>
    public string OutputFileExtension => ".txt";

    /// <inheritdoc/>
    public Task<Stream> TranslateAsync(Stream input, CancellationToken cancellationToken = default)
        => LibreOfficeConverter.ConvertAsync(input, ".odt", TextFilter, ".txt", cancellationToken);
}
