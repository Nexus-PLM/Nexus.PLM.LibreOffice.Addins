using System;
using System.Globalization;

namespace Nexus.PLM.LibreOffice.Templates
{
    /// <summary>
    /// How a PLM value — always text — is written into an ODF user-defined field of a given type.
    /// <para>
    /// This is the same three-way decision the Office add-ins make (<c>DocumentPropertyValue</c> for
    /// the open document, <c>CustomPropertyWrite</c> for the closed one): write it, leave the field
    /// alone, or give up on the type and store text. Office arrived at it the hard way — writing a
    /// string into a Date property threw <c>DISP_E_TYPEMISMATCH</c> and, because every property was
    /// written inside one try, that first failure stopped every later field being filled. The
    /// OpenXml half then drifted from the COM half and blanked typed fields an empty value should
    /// have left alone. Both mistakes are cheaper to inherit the answer to than to repeat.
    /// </para>
    /// <para>
    /// ODF declares a field's type as <c>meta:value-type</c>: <c>string</c> (or the attribute
    /// absent), <c>float</c>, <c>date</c>, <c>time</c> or <c>boolean</c>.
    /// </para>
    /// </summary>
    public static class OdfValueWrite
    {
        /// <summary>The <c>meta:value-type</c> values ODF defines for a user-defined field.</summary>
        public static class ValueTypes
        {
            /// <summary>Text. Also what a field with no <c>meta:value-type</c> attribute is.</summary>
            public const string String = "string";
            /// <summary>A number. ODF has one numeric type, not the integer/decimal pair Office has.</summary>
            public const string Float = "float";
            /// <summary>A date, or a date and time.</summary>
            public const string Date = "date";
            /// <summary>A duration.</summary>
            public const string Time = "time";
            /// <summary>True/false.</summary>
            public const string Boolean = "boolean";
        }

        /// <summary>What to do with a field.</summary>
        public enum Action
        {
            /// <summary>Write the value, keeping the field's declared type.</summary>
            Set,

            /// <summary>
            /// Leave the field exactly as it is: an empty value cannot be a date, a number, a
            /// duration or a boolean, and blanking one would lose the template author's value
            /// while claiming PLM had supplied something.
            /// </summary>
            Keep,

            /// <summary>
            /// The value cannot be expressed in the field's type, so the field becomes a string one
            /// holding it. The document then shows what PLM actually holds rather than a stale
            /// value that merely has the right type.
            /// </summary>
            ReplaceWithString,
        }

        /// <summary>
        /// The write for <paramref name="text"/> into a field of <paramref name="valueType"/>.
        /// </summary>
        /// <param name="valueType">The field's <c>meta:value-type</c>. Null, empty or unrecognised
        /// is treated as <see cref="ValueTypes.String"/>, which is what ODF means by its absence.</param>
        /// <param name="text">The value PLM holds.</param>
        /// <param name="lexical">What belongs in the element: the ODF lexical form for
        /// <see cref="Action.Set"/>, the text itself for <see cref="Action.ReplaceWithString"/>,
        /// and <see langword="null"/> for <see cref="Action.Keep"/>.</param>
        public static Action Decide(string? valueType, string? text, out string? lexical)
        {
            var declared = Normalise(valueType);
            var value    = text ?? string.Empty;
            var trimmed  = value.Trim();

            if (declared == ValueTypes.String)
            {
                // A string field is the one that may legitimately be emptied: nothing is lost that
                // was not text in the first place, and "" is a value a description can have.
                lexical = value;
                return Action.Set;
            }

            lexical = null;
            if (trimmed.Length == 0) return Action.Keep;

            switch (declared)
            {
                case ValueTypes.Date when TryDate(trimmed, out var date):
                    // ODF wants an xsd:dateTime with no zone — LibreOffice writes
                    // "2026-01-02T03:04:05" and shows it in the reader's own locale.
                    lexical = date.ToString("yyyy-MM-dd'T'HH:mm:ss", CultureInfo.InvariantCulture);
                    return Action.Set;

                case ValueTypes.Float when double.TryParse(
                        trimmed, NumberStyles.Float, CultureInfo.InvariantCulture, out var number):
                    lexical = number.ToString("R", CultureInfo.InvariantCulture);
                    return Action.Set;

                case ValueTypes.Boolean when TryBool(trimmed, out var flag):
                    lexical = flag ? "true" : "false";
                    return Action.Set;

                case ValueTypes.Time when TryTime(trimmed, out var duration):
                    lexical = duration;
                    return Action.Set;

                default:
                    lexical = value;
                    return Action.ReplaceWithString;
            }
        }

        /// <summary>
        /// The <c>meta:value-type</c> a field should carry after a write, given what it declared and
        /// what was decided.
        /// </summary>
        public static string? TypeAfter(string? valueType, Action action)
        {
            if (action == Action.ReplaceWithString) return ValueTypes.String;

            var declared = Normalise(valueType);

            // A field that declared nothing is a string field, and stays one without the attribute
            // being invented — LibreOffice omits it on the fields it considers plain text.
            return declared == ValueTypes.String && string.IsNullOrWhiteSpace(valueType)
                ? null
                : declared;
        }

        private static string Normalise(string? valueType)
        {
            if (string.IsNullOrWhiteSpace(valueType)) return ValueTypes.String;

            switch (valueType!.Trim().ToLowerInvariant())
            {
                case ValueTypes.Float:   return ValueTypes.Float;
                case ValueTypes.Date:    return ValueTypes.Date;
                case ValueTypes.Time:    return ValueTypes.Time;
                case ValueTypes.Boolean: return ValueTypes.Boolean;
                default:                 return ValueTypes.String;
            }
        }

        private static bool TryDate(string text, out DateTime date)
        {
            // A bare calendar date is that day wherever the reader is — never shifted by a zone.
            if (DateTime.TryParseExact(text, "yyyy-MM-dd", CultureInfo.InvariantCulture,
                                       DateTimeStyles.None, out date))
                return true;

            var hasZone = text.EndsWith("Z", StringComparison.OrdinalIgnoreCase)
                       || (text.Length > 19 && (text.LastIndexOf('+') > 10 || text.LastIndexOf('-') > 10));
            if (hasZone && DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture,
                                                   DateTimeStyles.None, out var offset))
            {
                // ODF has nowhere to put an offset, so it is resolved to local time as the reader
                // would see it, exactly as the Office halves do.
                date = offset.LocalDateTime;
                return true;
            }

            return DateTime.TryParse(text, CultureInfo.InvariantCulture,
                                     DateTimeStyles.AllowWhiteSpaces, out date);
        }

        private static bool TryBool(string text, out bool value)
        {
            switch (text.ToLowerInvariant())
            {
                case "true": case "yes": case "y": case "1": value = true;  return true;
                case "false": case "no": case "n": case "0": value = false; return true;
                default: value = false; return false;
            }
        }

        /// <summary>
        /// An xsd:duration, which is what an ODF <c>time</c> field holds. A value already in that
        /// form is kept; a plain clock time is converted.
        /// </summary>
        private static bool TryTime(string text, out string? duration)
        {
            if (text.StartsWith("P", StringComparison.OrdinalIgnoreCase)
             || text.StartsWith("-P", StringComparison.OrdinalIgnoreCase))
            {
                duration = text;
                return true;
            }

            if (TimeSpan.TryParse(text, CultureInfo.InvariantCulture, out var span))
            {
                duration = string.Format(
                    CultureInfo.InvariantCulture, "PT{0}H{1}M{2}S",
                    (int)span.TotalHours, span.Minutes, span.Seconds);
                return true;
            }

            duration = null;
            return false;
        }
    }
}
