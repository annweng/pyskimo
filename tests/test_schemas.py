"""
Unit tests for Pydantic schema models.

These tests verify schema validation, field constraints,
and data transformation methods.
"""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from pyskimo.schemas import (
    Athlete,
    Event,
    RaceFormat,
    RaceResult,
    ResultStatus,
    SeasonCalendar,
    Split,
)


class TestAthleteSchema:
    """Tests for Athlete model."""

    def test_basic_athlete(self) -> None:
        """Test creating a basic athlete."""
        athlete = Athlete(full_name="John Smith")
        assert athlete.full_name == "John Smith"
        assert athlete.nationality is None

    def test_athlete_with_all_fields(self) -> None:
        """Test athlete with all fields populated."""
        athlete = Athlete(
            athlete_id="12345",
            first_name="John",
            last_name="Smith",
            full_name="John Smith",
            nationality="USA",
            birth_year=1990,
            category="Senior Men",
            team="Alpine Racing Club",
        )
        assert athlete.athlete_id == "12345"
        assert athlete.first_name == "John"
        assert athlete.last_name == "Smith"
        assert athlete.nationality == "USA"
        assert athlete.birth_year == 1990

    def test_nationality_normalization(self) -> None:
        """Test nationality is uppercased."""
        athlete = Athlete(full_name="Test", nationality="usa")
        assert athlete.nationality == "USA"

        athlete2 = Athlete(full_name="Test", nationality="esp")
        assert athlete2.nationality == "ESP"

    def test_empty_nationality_becomes_none(self) -> None:
        """Test empty nationality is converted to None."""
        athlete = Athlete(full_name="Test", nationality="")
        assert athlete.nationality is None

    def test_invalid_nationality_length(self) -> None:
        """Test invalid nationality codes are handled."""
        athlete = Athlete(full_name="Test", nationality="X")
        assert athlete.nationality is None

    def test_empty_full_name_raises(self) -> None:
        """Test that empty full_name raises validation error."""
        with pytest.raises(ValidationError):
            Athlete(full_name="")

        with pytest.raises(ValidationError):
            Athlete(full_name="   ")

    def test_athlete_is_frozen(self) -> None:
        """Test that Athlete instances are immutable."""
        athlete = Athlete(full_name="John Smith")
        with pytest.raises(ValidationError):
            athlete.full_name = "Jane Doe"


class TestSplitSchema:
    """Tests for Split model."""

    def test_basic_split(self) -> None:
        """Test creating a basic split."""
        split = Split(name="T1", time_raw="10:23.4", time_seconds=623.4)
        assert split.name == "T1"
        assert split.time_raw == "10:23.4"
        assert split.time_seconds == 623.4

    def test_split_with_rank(self) -> None:
        """Test split with rank information."""
        split = Split(name="Summit", time_seconds=1234.5, rank=3)
        assert split.rank == 3

    def test_time_raw_normalization(self) -> None:
        """Test time_raw is stripped of whitespace."""
        split = Split(name="T1", time_raw="  10:23.4  ")
        assert split.time_raw == "10:23.4"

    def test_empty_time_raw_becomes_none(self) -> None:
        """Test empty time_raw is converted to None."""
        split = Split(name="T1", time_raw="")
        assert split.time_raw is None

    def test_negative_time_raises(self) -> None:
        """Test negative time_seconds raises error."""
        with pytest.raises(ValidationError):
            Split(name="T1", time_seconds=-10.0)


class TestRaceResultSchema:
    """Tests for RaceResult model."""

    def test_basic_result(self) -> None:
        """Test creating a basic race result."""
        athlete = Athlete(full_name="John Smith", nationality="USA")
        result = RaceResult(
            athlete=athlete,
            rank=1,
            time_raw="1:23:45.6",
            time_seconds=5025.6,
        )
        assert result.rank == 1
        assert result.status == ResultStatus.FINISHED
        assert result.time_seconds == 5025.6

    def test_result_with_splits(self) -> None:
        """Test result with intermediate splits."""
        athlete = Athlete(full_name="John Smith")
        splits = [
            Split(name="T1", time_seconds=600.0),
            Split(name="T2", time_seconds=1200.0),
        ]
        result = RaceResult(
            athlete=athlete,
            rank=1,
            time_seconds=1800.0,
            splits=splits,
        )
        assert len(result.splits) == 2
        assert result.splits[0].name == "T1"

    def test_dnf_result(self) -> None:
        """Test DNF result has no time."""
        athlete = Athlete(full_name="John Smith")
        result = RaceResult(
            athlete=athlete,
            status=ResultStatus.DNF,
        )
        assert result.status == ResultStatus.DNF
        assert result.time_seconds is None
        assert result.rank is None

    def test_time_delta_consistency(self) -> None:
        """Test that time_delta matches time_seconds when both present."""
        athlete = Athlete(full_name="John Smith")

        with pytest.raises(ValidationError):
            RaceResult(
                athlete=athlete,
                time_seconds=100.0,
                time_delta=timedelta(seconds=200.0),
            )

        result = RaceResult(
            athlete=athlete,
            time_seconds=100.0,
            time_delta=timedelta(seconds=100.0),
        )
        assert result.time_seconds == result.time_delta.total_seconds()

    def test_to_flat_dict(self) -> None:
        """Test flattening result for DataFrame conversion."""
        athlete = Athlete(
            full_name="John Smith",
            nationality="USA",
            category="Senior Men",
        )
        result = RaceResult(
            event_id="test-event",
            race_id="test-race",
            athlete=athlete,
            rank=1,
            bib="42",
            time_seconds=1234.5,
            status=ResultStatus.FINISHED,
        )

        flat = result.to_flat_dict()

        assert flat["event_id"] == "test-event"
        assert flat["race_id"] == "test-race"
        assert flat["athlete_full_name"] == "John Smith"
        assert flat["athlete_nationality"] == "USA"
        assert flat["rank"] == 1
        assert flat["bib"] == "42"
        assert flat["status"] == "finished"
        assert flat["time_seconds"] == 1234.5

    def test_to_flat_dict_with_splits(self) -> None:
        """Test flattening includes splits as separate columns."""
        athlete = Athlete(full_name="John Smith")
        splits = [
            Split(name="T1", time_seconds=600.0, rank=2),
            Split(name="T2", time_seconds=1200.0, rank=1),
        ]
        result = RaceResult(
            athlete=athlete,
            splits=splits,
        )

        flat = result.to_flat_dict()

        assert flat["split_1_name"] == "T1"
        assert flat["split_1_time_seconds"] == 600.0
        assert flat["split_1_rank"] == 2
        assert flat["split_2_name"] == "T2"

    def test_penalty_fields(self) -> None:
        """Test penalty fields."""
        athlete = Athlete(full_name="John Smith")
        result = RaceResult(
            athlete=athlete,
            penalty_seconds=30.0,
            penalty_reason="Equipment violation",
        )
        assert result.penalty_seconds == 30.0
        assert result.penalty_reason == "Equipment violation"


class TestEventSchema:
    """Tests for Event model."""

    def test_basic_event(self) -> None:
        """Test creating a basic event."""
        event = Event(
            event_id="wc-andorra-2024",
            name="World Cup Andorra",
        )
        assert event.event_id == "wc-andorra-2024"
        assert event.name == "World Cup Andorra"

    def test_event_with_all_fields(self) -> None:
        """Test event with all fields populated."""
        event = Event(
            event_id="wc-andorra-2024",
            name="World Cup Andorra",
            location="Andorra la Vella",
            country="AND",
            start_date="2024-01-15",
            end_date="2024-01-17",
            season="2023-2024",
            competition_type="World Cup",
            races=["sprint-men", "sprint-women", "individual-men"],
        )
        assert event.location == "Andorra la Vella"
        assert event.country == "AND"
        assert len(event.races) == 3

    def test_country_normalization(self) -> None:
        """Test country code is uppercased."""
        event = Event(event_id="test", name="Test", country="fra")
        assert event.country == "FRA"


class TestSeasonCalendarSchema:
    """Tests for SeasonCalendar model."""

    def test_basic_calendar(self) -> None:
        """Test creating a basic calendar."""
        calendar = SeasonCalendar(season="2023-2024")
        assert calendar.season == "2023-2024"
        assert calendar.events == []

    def test_calendar_with_events(self) -> None:
        """Test calendar with events."""
        events = [
            Event(event_id="wc-1", name="World Cup 1"),
            Event(event_id="wc-2", name="World Cup 2"),
        ]
        calendar = SeasonCalendar(
            season="2023-2024",
            events=events,
        )
        assert len(calendar.events) == 2

    def test_to_dataframe_records(self) -> None:
        """Test converting calendar to DataFrame records."""
        events = [
            Event(
                event_id="wc-1",
                name="World Cup 1",
                location="Location 1",
                country="ITA",
            ),
            Event(
                event_id="wc-2",
                name="World Cup 2",
                location="Location 2",
                country="FRA",
            ),
        ]
        calendar = SeasonCalendar(
            season="2023-2024",
            events=events,
        )

        records = calendar.to_dataframe_records()

        assert len(records) == 2
        assert records[0]["event_id"] == "wc-1"
        assert records[0]["name"] == "World Cup 1"
        assert records[1]["country"] == "FRA"


class TestRaceFormatEnum:
    """Tests for RaceFormat enumeration."""

    def test_all_formats(self) -> None:
        """Test all race format values."""
        assert RaceFormat.SPRINT.value == "sprint"
        assert RaceFormat.VERTICAL.value == "vertical"
        assert RaceFormat.INDIVIDUAL.value == "individual"
        assert RaceFormat.MIXED_RELAY.value == "mixed_relay"
        assert RaceFormat.TEAM.value == "team"
        assert RaceFormat.LONG_DISTANCE.value == "long_distance"
        assert RaceFormat.UNKNOWN.value == "unknown"


class TestResultStatusEnum:
    """Tests for ResultStatus enumeration."""

    def test_all_statuses(self) -> None:
        """Test all result status values."""
        assert ResultStatus.FINISHED.value == "finished"
        assert ResultStatus.DNF.value == "dnf"
        assert ResultStatus.DNS.value == "dns"
        assert ResultStatus.DSQ.value == "dsq"
        assert ResultStatus.LAP.value == "lap"
        assert ResultStatus.OTL.value == "otl"
        assert ResultStatus.PENDING.value == "pending"
