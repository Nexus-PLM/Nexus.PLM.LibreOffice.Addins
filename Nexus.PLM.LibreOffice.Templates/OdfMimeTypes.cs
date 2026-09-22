using System;
using System.Collections.Generic;
using System.Linq;

namespace Nexus.PLM.LibreOffice.Templates
{
    /// <summary>
    /// The OpenDocument MIME types this connector handles — one document type and one template type
    /// for each of the five LibreOffice applications.
    /// <para>
    /// The template types matter as much as the document ones: an admin uploads a <c>.ott</c> to a
    /// PLM type and the Vault asks an inspector what fields it has, so a missing template MIME row
    /// means the type cannot be given a template at all. The Office add-ins are still missing
    /// <c>.potx</c> and <c>.xltx</c> for exactly that reason, so they are all listed here from the
    /// start.
    /// </para>
    /// </summary>
    public static class OdfMimeTypes
    {
        private const string Prefix = "application/vnd.oasis.opendocument.";

        /// <summary>Writer — <c>.odt</c>.</summary>
        public const string Text = Prefix + "text";
        /// <summary>A Writer template — <c>.ott</c>.</summary>
        public const string TextTemplate = Prefix + "text-template";

        /// <summary>Calc — <c>.ods</c>.</summary>
        public const string Spreadsheet = Prefix + "spreadsheet";
        /// <summary>A Calc template — <c>.ots</c>.</summary>
        public const string SpreadsheetTemplate = Prefix + "spreadsheet-template";

        /// <summary>Impress — <c>.odp</c>.</summary>
        public const string Presentation = Prefix + "presentation";
        /// <summary>An Impress template — <c>.otp</c>.</summary>
        public const string PresentationTemplate = Prefix + "presentation-template";

        /// <summary>Draw — <c>.odg</c>.</summary>
        public const string Graphics = Prefix + "graphics";
        /// <summary>A Draw template — <c>.otg</c>.</summary>
        public const string GraphicsTemplate = Prefix + "graphics-template";

        /// <summary>Math — <c>.odf</c>.</summary>
        public const string Formula = Prefix + "formula";
        /// <summary>A Math template — <c>.otf</c>.</summary>
        public const string FormulaTemplate = Prefix + "formula-template";

        /// <summary>Every type above, documents and templates alike.</summary>
        public static IReadOnlyList<string> All { get; } = new[]
        {
            Text,         TextTemplate,
            Spreadsheet,  SpreadsheetTemplate,
            Presentation, PresentationTemplate,
            Graphics,     GraphicsTemplate,
            Formula,      FormulaTemplate,
        };

        /// <summary>The file extension a MIME type is normally stored under, without the dot.</summary>
        private static readonly Dictionary<string, string> Extensions =
            new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
            {
                [Text]         = "odt", [TextTemplate]         = "ott",
                [Spreadsheet]  = "ods", [SpreadsheetTemplate]  = "ots",
                [Presentation] = "odp", [PresentationTemplate] = "otp",
                [Graphics]     = "odg", [GraphicsTemplate]     = "otg",
                [Formula]      = "odf", [FormulaTemplate]      = "otf",
            };

        /// <summary>Whether this connector handles <paramref name="mimeType"/>.</summary>
        public static bool IsSupported(string? mimeType) =>
            mimeType is not null && Extensions.ContainsKey(mimeType.Trim());

        /// <summary>
        /// The extension for a MIME type, with its dot (e.g. <c>".odt"</c>), or
        /// <see langword="null"/> when it is not one of these.
        /// </summary>
        public static string? ExtensionFor(string? mimeType) =>
            mimeType is not null && Extensions.TryGetValue(mimeType.Trim(), out var extension)
                ? "." + extension
                : null;

        /// <summary>Every extension this connector handles, as <c>".odt;.ott;…"</c>.</summary>
        /// <remarks>
        /// This is the form a host declares in its own configuration and sends on <c>/plm/open</c>
        /// as <c>file_extensions</c>, so the browser lists only what it can actually open. The
        /// service keeps no list of hosts; each one says what it is capable of.
        /// </remarks>
        public static string ExtensionList => string.Join(";", All.Select(ExtensionFor).Distinct());
    }
}
