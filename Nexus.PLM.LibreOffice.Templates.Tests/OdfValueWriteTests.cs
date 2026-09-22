using System.Globalization;
using FluentAssertions;

namespace Nexus.PLM.LibreOffice.Templates.Tests;

/// <summary>
/// The one rule for putting a PLM value into a typed field.
/// <para>
/// The Office add-ins learned this twice over. Writing a string into a Date property threw
/// <c>DISP_E_TYPEMISMATCH</c> and, because every property was written inside one try, that first
/// failure stopped every later field being filled. Then the two halves drifted, and the OpenXml one
/// blanked a typed field that an empty value should have left alone. Both are cheaper to inherit the
/// answer to than to repeat here.
/// </para>
/// </summary>
public class OdfValueWriteTests
{
    private static (OdfValueWrite.Action Action, string? Lexical) Decide(string? type, string? text)
    {
        var action = OdfValueWrite.Decide(type, text, out var lexical);
        return (action, lexical);
    }

    // ── A string field ───────────────────────────────────────────────────────

    [Theory]
    [InlineData("string")]
    [InlineData("STRING")]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("something ODF has never heard of")]
    public void AStringField_TakesAnythingIncludingNothing(string? declared)
    {
        Decide(declared, "EM-00000039-DOC").Should().Be((OdfValueWrite.Action.Set, "EM-00000039-DOC"));

        // A description really can be emptied, and nothing typed is lost by doing it.
        Decide(declared, "").Should().Be((OdfValueWrite.Action.Set, ""));
    }

    /// <summary>A field that declared no type stays that way rather than gaining one.</summary>
    [Fact]
    public void AFieldThatDeclaredNoType_IsNotGivenOne()
        => OdfValueWrite.TypeAfter(null, OdfValueWrite.Action.Set).Should().BeNull();

    [Fact]
    public void AFieldThatDeclaredStringExplicitly_KeepsSayingSo()
        => OdfValueWrite.TypeAfter("string", OdfValueWrite.Action.Set).Should().Be("string");

    // ── Typed fields, and the empty value ────────────────────────────────────

    [Theory]
    [InlineData("date")]
    [InlineData("float")]
    [InlineData("boolean")]
    [InlineData("time")]
    public void AnEmptyValue_LeavesATypedFieldAlone(string declared)
    {
        // Not "writes an empty date" — there is no such thing, and blanking it would throw away the
        // template author's value while claiming PLM had supplied something.
        Decide(declared, "").Action.Should().Be(OdfValueWrite.Action.Keep);
        Decide(declared, "   ").Action.Should().Be(OdfValueWrite.Action.Keep);
        Decide(declared, null).Action.Should().Be(OdfValueWrite.Action.Keep);
    }

    [Theory]
    [InlineData("42", "42")]
    [InlineData(" 42 ", "42")]
    [InlineData("-7", "-7")]
    [InlineData("3.5", "3.5")]
    [InlineData("1e3", "1000")]
    public void ANumber_IsWrittenInvariantly(string text, string expected)
        => Decide("float", text).Should().Be((OdfValueWrite.Action.Set, expected));

    [Theory]
    [InlineData("true", "true")]
    [InlineData("TRUE", "true")]
    [InlineData("yes", "true")]
    [InlineData("y", "true")]
    [InlineData("1", "true")]
    [InlineData("false", "false")]
    [InlineData("No", "false")]
    [InlineData("0", "false")]
    public void AYesOrNo_IsWrittenAsOdfSpellsIt(string text, string expected)
        => Decide("boolean", text).Should().Be((OdfValueWrite.Action.Set, expected));

    /// <summary>
    /// A bare calendar date is that day wherever the reader is. Shifting it by a time zone is how a
    /// release date becomes the day before for half the company.
    /// </summary>
    [Fact]
    public void ABareDate_IsNotShiftedByATimeZone()
        => Decide("date", "2026-09-20").Should().Be((OdfValueWrite.Action.Set, "2026-09-20T00:00:00"));

    /// <summary>ODF has nowhere to put an offset, so an instant is resolved to local time.</summary>
    [Fact]
    public void AnInstantWithAZone_BecomesLocalTime()
    {
        var (action, lexical) = Decide("date", "2026-09-21T00:19:54.9158333Z");

        action.Should().Be(OdfValueWrite.Action.Set);
        var expected = new DateTimeOffset(2026, 9, 21, 0, 19, 54, TimeSpan.Zero)
            .LocalDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss", CultureInfo.InvariantCulture);
        lexical.Should().Be(expected);
    }

    [Theory]
    [InlineData("PT1H30M0S", "PT1H30M0S")]
    [InlineData("01:30:00", "PT1H30M0S")]
    public void ADuration_IsWrittenAsAnXsdDuration(string text, string expected)
        => Decide("time", text).Should().Be((OdfValueWrite.Action.Set, expected));

    // ── A value the type cannot hold ─────────────────────────────────────────

    [Theory]
    [InlineData("float", "seven")]
    [InlineData("date", "not a date")]
    [InlineData("boolean", "maybe")]
    [InlineData("time", "half past")]
    public void AValueTheTypeCannotHold_BecomesAStringField(string declared, string text)
    {
        var (action, lexical) = Decide(declared, text);

        // Better that the document shows what PLM holds than a stale value of the right type.
        action.Should().Be(OdfValueWrite.Action.ReplaceWithString);
        lexical.Should().Be(text);
        OdfValueWrite.TypeAfter(declared, action).Should().Be("string");
    }
}
