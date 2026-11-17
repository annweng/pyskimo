"""
Unit tests for time parsing utilities and edge case handling.

These tests cover:
- Time string parsing in various formats
- Status code detection (DNF, DNS, DSQ, etc.)
- Name normalization
- Rank parsing
"""

from datetime import timedelta

import pytest

from pyskimo.utils import (
    extract_nationality_from_name,
    is_status_code,
    normalize_name,
    parse_bib_number,
    parse_gap_time,
    parse_rank,
    parse_status_code,
    parse_time_to_seconds,
    parse_time_to_timedelta,
    seconds_to_time_string,
)


class TestParseTimeToSeconds:
    """Tests for parse_time_to_seconds function."""

    def test_hms_format(self) -> None:
        """Test hours:minutes:seconds format."""
        assert parse_time_to_seconds("1:23:45") == 5025.0
        assert parse_time_to_seconds("0:23:45") == 1425.0
        assert parse_time_to_seconds("12:00:00") == 43200.0

    def test_hms_with_milliseconds(self) -> None:
        """Test HH:MM:SS.ms format."""
        assert parse_time_to_seconds("1:23:45.6") == 5025.6
        assert parse_time_to_seconds("1:23:45.67") == 5025.67
        assert parse_time_to_seconds("1:23:45.678") == 5025.678
        assert parse_time_to_seconds("0:00:01.5") == 1.5

    def test_minutes_seconds_format(self) -> None:
        """Test MM:SS format."""
        assert parse_time_to_seconds("23:45") == 1425.0
        assert parse_time_to_seconds("1:30") == 90.0
        assert parse_time_to_seconds("0:45") == 45.0

    def test_minutes_seconds_with_ms(self) -> None:
        """Test MM:SS.ms format."""
        assert parse_time_to_seconds("23:45.5") == 1425.5
        assert parse_time_to_seconds("1:30.25") == 90.25

    def test_gap_format_positive(self) -> None:
        """Test positive gap times with + prefix."""
        assert parse_time_to_seconds("+0:12.34") == 12.34
        assert parse_time_to_seconds("+1:23.4") == 83.4
        assert parse_time_to_seconds("+0:05") == 5.0

    def test_gap_format_negative(self) -> None:
        """Test negative gap times with - prefix."""
        result = parse_time_to_seconds("-0:12.34")
        assert result is not None
        assert result == pytest.approx(-12.34)

    def test_seconds_only(self) -> None:
        """Test seconds-only format."""
        assert parse_time_to_seconds("45") == 45.0
        assert parse_time_to_seconds("45.5") == 45.5
        assert parse_time_to_seconds("120 sec") == 120.0

    def test_none_and_empty(self) -> None:
        """Test None and empty string handling."""
        assert parse_time_to_seconds(None) is None
        assert parse_time_to_seconds("") is None
        assert parse_time_to_seconds("   ") is None

    def test_status_codes_return_none(self) -> None:
        """Test that status codes return None."""
        assert parse_time_to_seconds("DNF") is None
        assert parse_time_to_seconds("DNS") is None
        assert parse_time_to_seconds("DSQ") is None
        assert parse_time_to_seconds("dnf") is None
        assert parse_time_to_seconds("Did Not Finish") is None

    def test_whitespace_handling(self) -> None:
        """Test whitespace is properly stripped."""
        assert parse_time_to_seconds("  1:23:45  ") == 5025.0
        assert parse_time_to_seconds("\t23:45\n") == 1425.0

    def test_quoted_times(self) -> None:
        """Test times with quote characters are handled."""
        assert parse_time_to_seconds("1:23:45") == 5025.0

    def test_parenthesized_times(self) -> None:
        """Test times in parentheses."""
        assert parse_time_to_seconds("(1:23:45)") == 5025.0
        assert parse_time_to_seconds("(+0:12)") == 12.0


class TestParseTimeToTimedelta:
    """Tests for parse_time_to_timedelta function."""

    def test_basic_conversion(self) -> None:
        """Test basic timedelta conversion."""
        result = parse_time_to_timedelta("1:23:45")
        assert result == timedelta(hours=1, minutes=23, seconds=45)

    def test_with_milliseconds(self) -> None:
        """Test timedelta with milliseconds."""
        result = parse_time_to_timedelta("1:23:45.5")
        assert result is not None
        assert result.total_seconds() == pytest.approx(5025.5)

    def test_none_for_status(self) -> None:
        """Test None returned for status codes."""
        assert parse_time_to_timedelta("DNF") is None
        assert parse_time_to_timedelta(None) is None


class TestSecondsToTimeString:
    """Tests for seconds_to_time_string function."""

    def test_with_hours(self) -> None:
        """Test formatting with hours included."""
        assert seconds_to_time_string(5025.6) == "1:23:45.600"
        assert seconds_to_time_string(3600.0) == "1:00:00.000"

    def test_without_hours(self) -> None:
        """Test formatting without hours."""
        assert seconds_to_time_string(125.5, include_hours=False) == "2:05.500"
        assert seconds_to_time_string(45.0, include_hours=False) == "0:45.000"

    def test_zero_seconds(self) -> None:
        """Test zero seconds."""
        assert seconds_to_time_string(0.0) == "0:00:00.000"

    def test_none_input(self) -> None:
        """Test None input returns None."""
        assert seconds_to_time_string(None) is None


class TestIsStatusCode:
    """Tests for is_status_code function."""

    def test_uppercase_codes(self) -> None:
        """Test uppercase status codes."""
        assert is_status_code("DNF") is True
        assert is_status_code("DNS") is True
        assert is_status_code("DSQ") is True
        assert is_status_code("LAP") is True
        assert is_status_code("OTL") is True

    def test_lowercase_codes(self) -> None:
        """Test lowercase status codes."""
        assert is_status_code("dnf") is True
        assert is_status_code("dns") is True
        assert is_status_code("dsq") is True

    def test_full_text_codes(self) -> None:
        """Test full text status descriptions."""
        assert is_status_code("Did Not Finish") is True
        assert is_status_code("did not start") is True
        assert is_status_code("disqualified") is True
        assert is_status_code("lapped") is True

    def test_non_status_values(self) -> None:
        """Test that times are not detected as status codes."""
        assert is_status_code("1:23:45") is False
        assert is_status_code("23:45") is False
        assert is_status_code("+0:12") is False
        assert is_status_code("John Smith") is False

    def test_empty_and_none(self) -> None:
        """Test empty and None values."""
        assert is_status_code("") is False
        assert is_status_code("   ") is False


class TestParseStatusCode:
    """Tests for parse_status_code function."""

    def test_standard_codes(self) -> None:
        """Test standard status code parsing."""
        assert parse_status_code("DNF") == "DNF"
        assert parse_status_code("DNS") == "DNS"
        assert parse_status_code("DSQ") == "DSQ"
        assert parse_status_code("LAP") == "LAP"
        assert parse_status_code("OTL") == "OTL"

    def test_case_insensitive(self) -> None:
        """Test case insensitivity."""
        assert parse_status_code("dnf") == "DNF"
        assert parse_status_code("Dnf") == "DNF"

    def test_full_text(self) -> None:
        """Test full text status descriptions."""
        assert parse_status_code("Did Not Finish") == "DNF"
        assert parse_status_code("did not start") == "DNS"
        assert parse_status_code("disqualified") == "DSQ"

    def test_with_reason(self) -> None:
        """Test status codes with reasons appended."""
        assert parse_status_code("dsq - equipment") == "DSQ"
        assert parse_status_code("DNF (crash)") == "DNF"

    def test_non_status(self) -> None:
        """Test non-status values return None."""
        assert parse_status_code("1:23:45") is None
        assert parse_status_code("") is None
        assert parse_status_code(None) is None


class TestNormalizeName:
    """Tests for normalize_name function."""

    def test_uppercase_lastname_first(self) -> None:
        """Test LASTNAME Firstname format."""
        assert normalize_name("SMITH John") == "John Smith"
        assert normalize_name("DE LA CRUZ Maria") == "Maria De La Cruz"

    def test_comma_separated(self) -> None:
        """Test lastname, firstname format."""
        assert normalize_name("Smith, John") == "John Smith"
        assert normalize_name("De La Cruz, Maria") == "Maria De La Cruz"

    def test_already_normalized(self) -> None:
        """Test already properly formatted names."""
        result = normalize_name("John Smith")
        assert result is not None
        assert result.lower() == "john smith"

    def test_extra_whitespace(self) -> None:
        """Test extra whitespace is removed."""
        assert normalize_name("  John   Smith  ") == "John Smith"

    def test_none_and_empty(self) -> None:
        """Test None and empty handling."""
        assert normalize_name(None) is None
        assert normalize_name("") is None


class TestParseRank:
    """Tests for parse_rank function."""

    def test_numeric_rank(self) -> None:
        """Test simple numeric ranks."""
        assert parse_rank("1") == 1
        assert parse_rank("12") == 12
        assert parse_rank("100") == 100

    def test_with_suffix(self) -> None:
        """Test ranks with ordinal suffixes."""
        assert parse_rank("1st") == 1
        assert parse_rank("2nd") == 2
        assert parse_rank("3rd") == 3
        assert parse_rank("12th") == 12

    def test_with_period(self) -> None:
        """Test ranks with trailing period."""
        assert parse_rank("1.") == 1
        assert parse_rank("12.") == 12

    def test_status_codes_return_none(self) -> None:
        """Test status codes return None."""
        assert parse_rank("DNF") is None
        assert parse_rank("DNS") is None

    def test_invalid_returns_none(self) -> None:
        """Test invalid values return None."""
        assert parse_rank("") is None
        assert parse_rank(None) is None
        assert parse_rank("abc") is None
        assert parse_rank("0") is None
        assert parse_rank("-1") is None


class TestParseBibNumber:
    """Tests for parse_bib_number function."""

    def test_numeric_bib(self) -> None:
        """Test simple numeric bibs."""
        assert parse_bib_number("42") == "42"
        assert parse_bib_number("1") == "1"

    def test_with_hash(self) -> None:
        """Test bibs with # prefix."""
        assert parse_bib_number("#42") == "42"
        assert parse_bib_number("# 42") == "42"

    def test_with_whitespace(self) -> None:
        """Test whitespace handling."""
        assert parse_bib_number("  42  ") == "42"

    def test_empty_and_none(self) -> None:
        """Test empty and None handling."""
        assert parse_bib_number(None) is None
        assert parse_bib_number("") is None


class TestParseGapTime:
    """Tests for parse_gap_time function."""

    def test_positive_gap(self) -> None:
        """Test positive gap times."""
        assert parse_gap_time("+1:23.4") == 83.4
        assert parse_gap_time("+0:05") == 5.0
        assert parse_gap_time("+2:30:00") == 9000.0

    def test_leader_indicators(self) -> None:
        """Test leader (zero gap) indicators."""
        assert parse_gap_time("-") == 0.0
        assert parse_gap_time("--") == 0.0
        assert parse_gap_time("0:00") == 0.0

    def test_none_handling(self) -> None:
        """Test None and empty handling."""
        assert parse_gap_time(None) is None
        assert parse_gap_time("") is None


class TestExtractNationalityFromName:
    """Tests for extract_nationality_from_name function."""

    def test_with_nationality(self) -> None:
        """Test name with nationality in parentheses."""
        name, nat = extract_nationality_from_name("John Smith (USA)")
        assert name == "John Smith"
        assert nat == "USA"

    def test_three_letter_code(self) -> None:
        """Test three-letter nationality codes."""
        name, nat = extract_nationality_from_name("Maria Garcia (ESP)")
        assert name == "Maria Garcia"
        assert nat == "ESP"

    def test_two_letter_code(self) -> None:
        """Test two-letter nationality codes."""
        name, nat = extract_nationality_from_name("Pierre Dupont (FR)")
        assert name == "Pierre Dupont"
        assert nat == "FR"

    def test_without_nationality(self) -> None:
        """Test name without nationality."""
        name, nat = extract_nationality_from_name("John Smith")
        assert name == "John Smith"
        assert nat is None

    def test_with_parentheses_not_nationality(self) -> None:
        """Test parentheses that aren't nationality codes."""
        name, nat = extract_nationality_from_name("John Smith (Jr)")
        assert name == "John Smith (Jr)"
        assert nat is None
