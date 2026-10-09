namespace Nexus.PLM.LibreOffice.Translators;

/// <summary>
/// The MIME values this repo's translators speak. Values follow the installation's format
/// catalog (the MIME Types app), which is the source of truth for format names.
/// </summary>
public static class MimeTypes
{
    /// <summary>OpenDocument text (<c>.odt</c>) — this repo's input format family.</summary>
    public const string Odt = "application/vnd.oasis.opendocument.text";

    /// <summary>Word document (<c>.docx</c>).</summary>
    public const string Docx = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

    /// <summary>PDF.</summary>
    public const string Pdf = "application/pdf";
}
