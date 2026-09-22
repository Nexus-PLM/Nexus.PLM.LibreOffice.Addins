using System.IO.Compression;
using System.Text;

namespace Nexus.PLM.LibreOffice.Templates.Tests;

/// <summary>
/// Builds OpenDocument packages for the tests to read and rewrite.
/// <para>
/// Hand-built rather than checked in as binary fixtures, so a test says in its own body what shape
/// of document it is about. The parts are the real thing — the namespaces, the
/// <c>office:document-meta</c> root and the <c>meta:value-type</c> attributes are all copied from
/// what LibreOffice 26.2 wrote when asked to save a document carrying user fields.
/// </para>
/// </summary>
internal static class OdfDocument
{
    private static readonly UTF8Encoding Utf8NoBom = new(encoderShouldEmitUTF8Identifier: false);

    internal const string MetaHeader =
        """<?xml version="1.0" encoding="UTF-8"?>""" +
        """<office:document-meta """ +
        """xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" """ +
        """xmlns:meta="urn:oasis:names:tc:opendocument:xmlns:meta:1.0" office:version="1.4">""";

    internal const string ContentHeader =
        """<?xml version="1.0" encoding="UTF-8"?>""" +
        """<office:document-content """ +
        """xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" """ +
        """xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" """ +
        """xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0" """ +
        """xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" office:version="1.4">""";

    /// <summary>One <c>meta:user-defined</c> element. A null type omits the attribute, as ODF allows.</summary>
    internal static string UserField(string name, string value, string? valueType = null) =>
        valueType is null
            ? $"""<meta:user-defined meta:name="{name}">{value}</meta:user-defined>"""
            : $"""<meta:user-defined meta:name="{name}" meta:value-type="{valueType}">{value}</meta:user-defined>""";

    /// <summary>A package with the given parts, <c>mimetype</c> first and stored, as ODF requires.</summary>
    internal static MemoryStream Package(
        string mimeType, string? metaBody = null, string? contentBody = null)
    {
        var stream = new MemoryStream();

        using (var zip = new ZipArchive(stream, ZipArchiveMode.Create, leaveOpen: true))
        {
            Write(zip, "mimetype", mimeType, CompressionLevel.NoCompression);

            Write(zip, "meta.xml",
                MetaHeader + "<office:meta>" + (metaBody ?? "") + "</office:meta></office:document-meta>");

            Write(zip, "content.xml",
                ContentHeader + "<office:body>" + (contentBody ?? "") + "</office:body></office:document-content>");
        }

        stream.Position = 0;
        return stream;
    }

    /// <summary>The usual Writer document: user fields only.</summary>
    internal static MemoryStream Writer(params string[] userFields) =>
        Package(OdfMimeTypes.Text, string.Concat(userFields));

    private static void Write(ZipArchive zip, string name, string text,
                              CompressionLevel level = CompressionLevel.Optimal)
    {
        var entry = zip.CreateEntry(name, level);
        using var writer = new StreamWriter(entry.Open(), Utf8NoBom);
        writer.Write(text);
    }

    /// <summary>The text of one part of a package.</summary>
    internal static string PartOf(Stream package, string entryName)
    {
        package.Position = 0;
        using var zip = new ZipArchive(package, ZipArchiveMode.Read, leaveOpen: true);
        using var reader = new StreamReader(zip.GetEntry(entryName)!.Open(), Utf8NoBom);
        return reader.ReadToEnd();
    }

    /// <summary>Every entry name, in archive order.</summary>
    internal static IReadOnlyList<string> EntryNames(Stream package)
    {
        package.Position = 0;
        using var zip = new ZipArchive(package, ZipArchiveMode.Read, leaveOpen: true);
        return zip.Entries.Select(e => e.FullName).ToList();
    }

    /// <summary>Whether an entry is stored uncompressed.</summary>
    internal static bool IsStored(Stream package, string entryName)
    {
        package.Position = 0;
        using var zip = new ZipArchive(package, ZipArchiveMode.Read, leaveOpen: true);
        var entry = zip.GetEntry(entryName)!;
        return entry.CompressedLength == entry.Length;
    }
}
