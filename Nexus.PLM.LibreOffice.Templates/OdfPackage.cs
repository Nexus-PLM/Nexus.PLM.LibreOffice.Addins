using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Text;
using System.Xml.Linq;

namespace Nexus.PLM.LibreOffice.Templates
{
    /// <summary>
    /// An OpenDocument file: a zip of XML parts. Reads one part, and rewrites a package with some
    /// parts replaced.
    /// <para>
    /// The ODF specification requires the <c>mimetype</c> entry to be <b>first</b> in the archive
    /// and <b>stored uncompressed</b>, so that a reader can identify the document from the first
    /// bytes of the file without inflating anything. A naive copy loop deflates it or moves it.
    /// <see cref="Rewrite"/> writes it back first and stored.
    /// </para>
    /// <para>
    /// Measured, so the reason here is honest rather than folklore: LibreOffice 26.2 <b>does</b>
    /// still open a package whose <c>mimetype</c> has been deflated, so this is not what keeps the
    /// file working in LibreOffice today. It is kept because the spec requires it, because the
    /// things that identify a file by magic bytes rely on it (a deflated entry defeats them), and
    /// because "LibreOffice currently tolerates it" is not a property worth depending on.
    /// </para>
    /// <para>
    /// Every LibreOffice application's format is one of these — text, spreadsheet, presentation,
    /// drawing and formula alike — which is why one implementation serves all five, where Office
    /// needed a connector per application.
    /// </para>
    /// </summary>
    internal static class OdfPackage
    {
        internal const string MimeTypeEntry = "mimetype";

        /// <summary>UTF-8 without a byte-order mark, which is what ODF parts are.</summary>
        private static readonly UTF8Encoding Utf8NoBom = new UTF8Encoding(encoderShouldEmitUTF8Identifier: false);

        /// <summary>
        /// One part, parsed. <see langword="null"/> when the package has no such part — a document
        /// with no metadata at all simply has no <c>meta.xml</c>, which is not an error.
        /// </summary>
        internal static XDocument? ReadPart(Stream package, string entryName)
        {
            using var zip = new ZipArchive(package, ZipArchiveMode.Read, leaveOpen: true);

            var entry = zip.GetEntry(entryName);
            if (entry is null) return null;

            using var stream = entry.Open();
            return XDocument.Load(stream);
        }

        /// <summary>The <c>mimetype</c> part's text, or an empty string when the package has none.</summary>
        internal static string ReadMimeType(Stream package)
        {
            using var zip = new ZipArchive(package, ZipArchiveMode.Read, leaveOpen: true);

            var entry = zip.GetEntry(MimeTypeEntry);
            if (entry is null) return string.Empty;

            using var reader = new StreamReader(entry.Open(), Utf8NoBom);
            return reader.ReadToEnd().Trim();
        }

        /// <summary>
        /// Copies <paramref name="source"/> to <paramref name="destination"/>, replacing the named
        /// parts with <paramref name="replacements"/> and leaving every other byte alone.
        /// </summary>
        /// <param name="source">The package to copy. Read from its current position.</param>
        /// <param name="destination">Where the new package is written.</param>
        /// <param name="replacements">Entry name to its new document. Names absent from the source
        /// are added; a source part with no replacement is copied verbatim.</param>
        internal static void Rewrite(
            Stream source, Stream destination, IReadOnlyDictionary<string, XDocument> replacements)
        {
            if (source      is null) throw new ArgumentNullException(nameof(source));
            if (destination is null) throw new ArgumentNullException(nameof(destination));
            if (replacements is null) throw new ArgumentNullException(nameof(replacements));

            using var read  = new ZipArchive(source, ZipArchiveMode.Read, leaveOpen: true);
            using var write = new ZipArchive(destination, ZipArchiveMode.Create, leaveOpen: true);

            var written = new HashSet<string>(StringComparer.Ordinal);

            // mimetype first, uncompressed — the whole reason this method exists.
            var mimeEntry = read.GetEntry(MimeTypeEntry);
            if (mimeEntry is not null)
            {
                var copy = write.CreateEntry(MimeTypeEntry, CompressionLevel.NoCompression);
                using var from = mimeEntry.Open();
                using var to   = copy.Open();
                from.CopyTo(to);
                written.Add(MimeTypeEntry);
            }

            foreach (var entry in read.Entries)
            {
                if (written.Contains(entry.FullName)) continue;
                written.Add(entry.FullName);

                if (replacements.TryGetValue(entry.FullName, out var replacement))
                {
                    WritePart(write, entry.FullName, replacement);
                    continue;
                }

                var copy = write.CreateEntry(entry.FullName, CompressionLevel.Optimal);
                using var from = entry.Open();
                using var to   = copy.Open();
                from.CopyTo(to);
            }

            // A replacement for a part the source did not have — a document that never carried
            // metadata being given some.
            foreach (var pair in replacements)
                if (!written.Contains(pair.Key))
                    WritePart(write, pair.Key, pair.Value);
        }

        private static void WritePart(ZipArchive zip, string entryName, XDocument document)
        {
            var entry = zip.CreateEntry(entryName, CompressionLevel.Optimal);
            using var stream = entry.Open();

            // XDocument.Save would emit its own declaration; ODF parts are UTF-8 with no BOM.
            using var writer = new StreamWriter(stream, Utf8NoBom);
            document.Save(writer, SaveOptions.DisableFormatting);
        }
    }
}
