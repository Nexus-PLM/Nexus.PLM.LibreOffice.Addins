using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Xml.Linq;
using Nexus.PLM.Addin.Sdk.Templates;

namespace Nexus.PLM.LibreOffice.Templates
{
    /// <summary>The kinds of field a LibreOffice document can carry.</summary>
    public static class FieldKinds
    {
        /// <summary>
        /// A user-defined document property (<c>meta:user-defined</c> in <c>meta.xml</c>). Every
        /// LibreOffice application supports these, so they are the one kind that works in all five.
        /// </summary>
        public const string UserField = "UserField";

        /// <summary>
        /// A named range in a Calc spreadsheet (<c>table:named-range</c>). The spreadsheet
        /// equivalent of Excel's defined names.
        /// </summary>
        public const string NamedRange = "NamedRange";

        /// <summary>
        /// A named frame or shape whose text can be driven — Writer text frames, and the shapes on
        /// an Impress slide or a Draw page.
        /// </summary>
        public const string NamedShape = "NamedShape";
    }

    /// <summary>
    /// Reads and writes the driveable fields of a LibreOffice document, through the file rather than
    /// through LibreOffice.
    /// <para>
    /// One connector serves Writer, Calc, Impress, Draw and Math. Every one of their formats is an
    /// OpenDocument package whose metadata lives in the same <c>meta.xml</c> under the same schema,
    /// so the only per-application difference is the MIME type and which of the three field kinds
    /// the document can hold. The Office add-ins needed a connector each, because a <c>.docx</c>'s
    /// parts, a <c>.xlsx</c>'s sheets and a <c>.pptx</c>'s slides have nothing in common.
    /// </para>
    /// <para>
    /// Pure XML over a zip: no LibreOffice installation, no automation, nothing proprietary
    /// redistributed. That is what lets the same assembly run server-side in the Vault's plugin
    /// host — listing a template's fields so mappings can be defined in the data modeller — and
    /// client-side against a staged file the application does not yet have open.
    /// </para>
    /// </summary>
    public sealed class LibreOfficeTemplateConnector : ITemplateInspector, ITemplateValueReader, ITemplateValueWriter
    {
        private const string MetaPart    = "meta.xml";
        private const string ContentPart = "content.xml";

        private static readonly XNamespace Meta   = "urn:oasis:names:tc:opendocument:xmlns:meta:1.0";
        private static readonly XNamespace Table  = "urn:oasis:names:tc:opendocument:xmlns:table:1.0";
        private static readonly XNamespace Draw   = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0";
        private static readonly XNamespace Text   = "urn:oasis:names:tc:opendocument:xmlns:text:1.0";

        /// <inheritdoc />
        public string AppKey => "libreoffice";

        /// <inheritdoc />
        public IReadOnlyList<string> SupportedMimeTypes => OdfMimeTypes.All;

        // ── Inspecting ───────────────────────────────────────────────────────

        /// <inheritdoc />
        public IReadOnlyList<TemplateField> GetFields(Stream templateStream)
        {
            if (templateStream is null) throw new ArgumentNullException(nameof(templateStream));

            var fields = new List<TemplateField>();
            var seen   = new HashSet<(string Kind, string Name)>();

            void Add(string? name, string kind)
            {
                if (string.IsNullOrWhiteSpace(name)) return;
                if (!seen.Add((kind, name!))) return;
                fields.Add(new TemplateField(name!, kind));
            }

            var start = templateStream.CanSeek ? templateStream.Position : 0L;

            foreach (var name in UserFieldNames(OdfPackage.ReadPart(templateStream, MetaPart)))
                Add(name, FieldKinds.UserField);

            if (templateStream.CanSeek) templateStream.Position = start;
            var content = OdfPackage.ReadPart(templateStream, ContentPart);

            foreach (var range in NamedRanges(content))
                Add(range, FieldKinds.NamedRange);

            foreach (var shape in NamedShapes(content))
                Add(shape, FieldKinds.NamedShape);

            return fields;
        }

        // ── Reading ──────────────────────────────────────────────────────────

        /// <inheritdoc />
        public IReadOnlyDictionary<string, string> ReadValues(
            Stream documentStream, IReadOnlyCollection<string>? fieldNames = null)
        {
            if (documentStream is null) throw new ArgumentNullException(nameof(documentStream));

            // Case-insensitively, as the contract specifies. A null or empty request means
            // everything the document has.
            var wanted = fieldNames is null || fieldNames.Count == 0
                ? null
                : new HashSet<string>(fieldNames, StringComparer.OrdinalIgnoreCase);
            bool Requested(string name) => wanted is null || wanted.Contains(name);

            var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            var start  = documentStream.CanSeek ? documentStream.Position : 0L;

            foreach (var field in UserFields(OdfPackage.ReadPart(documentStream, MetaPart)))
            {
                var name = (string?)field.Attribute(Meta + "name");
                if (!string.IsNullOrWhiteSpace(name) && Requested(name!)) values[name!] = field.Value;
            }

            if (documentStream.CanSeek) documentStream.Position = start;
            var content = OdfPackage.ReadPart(documentStream, ContentPart);

            // A user field wins over a shape of the same name: it is the one the document itself
            // treats as a property, and the one every application can carry.
            foreach (var shape in ShapeElements(content))
            {
                var name = NameOf(shape);
                if (string.IsNullOrWhiteSpace(name) || !Requested(name!) || values.ContainsKey(name!))
                    continue;

                var text = ShapeText(shape);
                if (text is not null) values[name!] = text;
            }

            return values;
        }

        // ── Writing ──────────────────────────────────────────────────────────

        /// <inheritdoc />
        public void WriteValues(
            Stream templateStream, Stream outputStream, IReadOnlyDictionary<string, string> values)
        {
            if (templateStream is null) throw new ArgumentNullException(nameof(templateStream));
            if (outputStream   is null) throw new ArgumentNullException(nameof(outputStream));
            if (values         is null) throw new ArgumentNullException(nameof(values));

            var start = templateStream.CanSeek ? templateStream.Position : 0L;

            var meta = OdfPackage.ReadPart(templateStream, MetaPart);
            if (templateStream.CanSeek) templateStream.Position = start;
            var content = OdfPackage.ReadPart(templateStream, ContentPart);

            // Built by hand: netstandard2.0's Dictionary has no IReadOnlyDictionary constructor.
            var byName = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
            foreach (var pair in values) byName[pair.Key] = pair.Value;

            var replacements = new Dictionary<string, XDocument>(StringComparer.Ordinal);
            if (meta    is not null && WriteUserFields(meta, byName))   replacements[MetaPart]    = meta;
            if (content is not null && WriteShapeText(content, byName)) replacements[ContentPart] = content;

            if (templateStream.CanSeek) templateStream.Position = start;
            OdfPackage.Rewrite(templateStream, outputStream, replacements);
        }

        /// <summary>
        /// Updates the user-defined fields the document already carries. Fields are not invented: a
        /// name nobody put in the template is not a field of it, and adding one would make the file
        /// claim a field it does not really have.
        /// </summary>
        /// <returns>Whether anything changed.</returns>
        private static bool WriteUserFields(XDocument meta, IReadOnlyDictionary<string, string> values)
        {
            var changed = false;

            foreach (var field in UserFields(meta))
            {
                var name = (string?)field.Attribute(Meta + "name");
                if (string.IsNullOrWhiteSpace(name)) continue;
                if (!values.TryGetValue(name!, out var value)) continue;

                var declared = (string?)field.Attribute(Meta + "value-type");
                var action   = OdfValueWrite.Decide(declared, value, out var lexical);
                if (action == OdfValueWrite.Action.Keep) continue;

                var typeAfter = OdfValueWrite.TypeAfter(declared, action);
                if (typeAfter is null) field.Attribute(Meta + "value-type")?.Remove();
                else                   field.SetAttributeValue(Meta + "value-type", typeAfter);

                field.Value = lexical ?? string.Empty;
                changed = true;
            }

            return changed;
        }

        /// <summary>
        /// Replaces the text of named frames and shapes, keeping the first run's formatting.
        /// <para>
        /// A template author chose a font, a size and a colour for that frame. Writing a fresh
        /// paragraph would discard all of it and put the revision on a page in whatever the
        /// document's default happens to be — the sort of thing nobody notices until it is printed.
        /// </para>
        /// </summary>
        private static bool WriteShapeText(XDocument content, IReadOnlyDictionary<string, string> values)
        {
            var changed = false;

            foreach (var shape in ShapeElements(content))
            {
                var name = NameOf(shape);
                if (string.IsNullOrWhiteSpace(name)) continue;
                if (!values.TryGetValue(name!, out var value)) continue;

                var paragraphs = shape.Elements(Text + "p").ToList();
                if (paragraphs.Count == 0)
                {
                    shape.Add(new XElement(Text + "p", value ?? string.Empty));
                    changed = true;
                    continue;
                }

                // Anything after the first paragraph is the old value's remainder.
                foreach (var extra in paragraphs.Skip(1)) extra.Remove();

                var first = paragraphs[0];
                var span  = first.Elements(Text + "span").FirstOrDefault();
                if (span is null)
                {
                    first.ReplaceNodes(new XText(value ?? string.Empty));
                }
                else
                {
                    foreach (var extra in first.Elements(Text + "span").Skip(1).ToList()) extra.Remove();
                    span.ReplaceNodes(new XText(value ?? string.Empty));
                }

                changed = true;
            }

            return changed;
        }

        // ── The document's shape ─────────────────────────────────────────────

        private static IEnumerable<XElement> UserFields(XDocument? meta) =>
            meta?.Descendants(Meta + "user-defined") ?? Enumerable.Empty<XElement>();

        private static IEnumerable<string?> UserFieldNames(XDocument? meta) =>
            UserFields(meta).Select(f => (string?)f.Attribute(Meta + "name"));

        private static IEnumerable<string?> NamedRanges(XDocument? content) =>
            content?.Descendants(Table + "named-range")
                    .Select(r => (string?)r.Attribute(Table + "name"))
            ?? Enumerable.Empty<string?>();

        /// <summary>
        /// The frames and shapes that can hold text, and that somebody deliberately named.
        /// <para>
        /// ODF needs no heuristic for this, and that is worth stating because the PowerPoint
        /// connector does: PowerPoint invents a name for every shape, so a slide full of
        /// "Title Placeholder 1" and "Content Placeholder 2" had to be told apart from real fields
        /// by guessing at the wording — which got it wrong twice before a real template settled it.
        /// </para>
        /// <para>
        /// LibreOffice does not do that. Measured against files LibreOffice 26.2 wrote itself: a
        /// frame the author named carries <c>draw:name</c>, and an untouched title placeholder or a
        /// freshly drawn box carries <b>no name attribute at all</b>. The Navigator's "Shape 1" is
        /// a display label, not something stored. So a name existing IS the signal, and no list of
        /// suspicious words is needed — one that existed would eventually exclude somebody's
        /// legitimately-named "Title 1".
        /// </para>
        /// </summary>
        private static IEnumerable<XElement> ShapeElements(XDocument? content) =>
            content?.Descendants()
                    .Where(e => e.Name == Draw + "frame" || e.Name == Draw + "custom-shape"
                             || e.Name == Draw + "text-box")
                    .Select(e => e.Name == Draw + "frame"
                        ? e.Elements(Draw + "text-box").FirstOrDefault() ?? e
                        : e)
                    .Where(e => !string.IsNullOrWhiteSpace(NameOf(e)))
            ?? Enumerable.Empty<XElement>();

        private static IEnumerable<string?> NamedShapes(XDocument? content) =>
            ShapeElements(content).Select(NameOf);

        /// <summary>
        /// A shape's name. A <c>draw:text-box</c> carries none itself — the name is on the
        /// <c>draw:frame</c> that holds it.
        /// </summary>
        private static string? NameOf(XElement element) =>
            (string?)element.Attribute(Draw + "name")
            ?? (string?)element.Parent?.Attribute(Draw + "name");

        /// <summary>The text of a shape, or <see langword="null"/> when it holds none.</summary>
        private static string? ShapeText(XElement shape)
        {
            var paragraphs = shape.Elements(Text + "p").ToList();
            if (paragraphs.Count == 0) return null;

            return string.Join(Environment.NewLine, paragraphs.Select(p => p.Value));
        }
    }
}
