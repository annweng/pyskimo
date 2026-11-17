"""
Pydantic models for Ski Mountaineering race data validation and normalization.

These schemas enforce strict validation on extracted race data before conversion
to pandas DataFrames, ensuring consistent handling of DNFs, DSQs, time penalties,
and various race formats (Sprint, Vertical, Individual, Mixed Relay).
"""

from __future__ import annotations

from datetime import timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RaceFormat(str, Enum):
    """Ski Mountaineering race formats."""

    SPRINT = "sprint"
    VERTICAL = "vertical"
    INDIVIDUAL = "individual"
    MIXED_RELAY = "mixed_relay"
    TEAM = "team"
    LONG_DISTANCE = "long_distance"
    UNKNOWN = "unknown"


class ResultStatus(str, Enum):
    """Status codes for race results."""

    FINISHED = "finished"
    DNF = "dnf"  # Did Not Finish
    DNS = "dns"  # Did Not Start
    DSQ = "dsq"  # Disqualified
    LAP = "lap"  # Lapped
    OTL = "otl"  # Outside Time Limit
    PENDING = "pending"


class Split(BaseModel):
    """
    A single timing split within a race.

    Splits track intermediate timing points, commonly used at transitions,
    climb summits, or relay handoffs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(..., description="Split point name (e.g., 'T1', 'Summit', 'Transition')")
    time_raw: str | None = Field(None, description="Raw time string as displayed")
    time_seconds: float | None = Field(None, ge=0, description="Time in seconds from race start")
    rank: int | None = Field(None, ge=1, description="Position at this split")

    @field_validator("time_raw", mode="before")
    @classmethod
    def normalize_time_raw(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip()


class Athlete(BaseModel):
    """
    Athlete identity and demographics.

    Stores athlete identification data with support for various naming conventions
    used across different data sources.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    athlete_id: str | None = Field(None, description="Unique athlete identifier from source")
    first_name: str | None = Field(None, description="Athlete first/given name")
    last_name: str | None = Field(None, description="Athlete family/surname")
    full_name: str = Field(..., description="Full display name")
    nationality: str | None = Field(
        None, min_length=2, max_length=3, description="ISO country code"
    )
    birth_year: int | None = Field(None, ge=1900, le=2020, description="Year of birth")
    category: str | None = Field(
        None, description="Age/gender category (e.g., 'Senior Men', 'U23 Women')"
    )
    team: str | None = Field(None, description="Team or club affiliation")

    @field_validator("nationality", mode="before")
    @classmethod
    def normalize_nationality(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        code = str(v).strip().upper()
        if len(code) < 2 or len(code) > 3:
            return None
        return code

    @model_validator(mode="after")
    def validate_name_consistency(self) -> Athlete:
        """Ensure full_name is populated even if first/last are missing."""
        if not self.full_name or self.full_name.strip() == "":
            raise ValueError("full_name must not be empty")
        return self


class RaceResult(BaseModel):
    """
    A single athlete's result in a Skimo race.

    This model handles the complexity of race results including:
    - Various finish statuses (DNF, DNS, DSQ, etc.)
    - Time penalties and adjustments
    - Multiple timing splits
    - Gap calculations to leader/previous
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str | None = Field(None, description="Event identifier from source")
    race_id: str | None = Field(None, description="Specific race identifier within event")
    race_format: RaceFormat = Field(RaceFormat.UNKNOWN, description="Race format type")

    athlete: Athlete = Field(..., description="Athlete information")
    bib: str | None = Field(None, description="Race bib number")

    rank: int | None = Field(None, ge=1, description="Final finishing position")
    status: ResultStatus = Field(ResultStatus.FINISHED, description="Result status")

    time_raw: str | None = Field(None, description="Raw finish time as displayed")
    time_seconds: float | None = Field(None, ge=0, description="Finish time in seconds")
    time_delta: timedelta | None = Field(None, description="Finish time as timedelta")

    gap_raw: str | None = Field(None, description="Raw gap to leader as displayed")
    gap_seconds: float | None = Field(None, ge=0, description="Gap to leader in seconds")

    penalty_seconds: float = Field(0, ge=0, description="Time penalties in seconds")
    penalty_reason: str | None = Field(None, description="Reason for penalty if applicable")

    splits: list[Split] = Field(default_factory=list, description="Intermediate timing splits")

    points: float | None = Field(None, ge=0, description="Race points awarded")

    @field_validator("time_raw", "gap_raw", mode="before")
    @classmethod
    def normalize_time_strings(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip()

    @field_validator("bib", mode="before")
    @classmethod
    def normalize_bib(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip()

    @model_validator(mode="after")
    def validate_time_consistency(self) -> RaceResult:
        """
        Ensure time fields are consistent with status.

        - Finished athletes should have time_seconds
        - Non-finished athletes may have None times
        - time_delta should match time_seconds if both present
        """
        if self.time_seconds is not None and self.time_delta is not None:
            expected_seconds = self.time_delta.total_seconds()
            if abs(self.time_seconds - expected_seconds) > 0.1:
                raise ValueError(
                    f"time_seconds ({self.time_seconds}) doesn't match "
                    f"time_delta ({expected_seconds})"
                )
        return self

    def to_flat_dict(self) -> dict[str, Any]:
        """
        Flatten result to a dictionary suitable for DataFrame conversion.

        Returns a flat dictionary with athlete fields prefixed with 'athlete_'
        and splits expanded into separate columns.
        """
        flat: dict[str, Any] = {
            "event_id": self.event_id,
            "race_id": self.race_id,
            "race_format": self.race_format.value,
            "athlete_id": self.athlete.athlete_id,
            "athlete_first_name": self.athlete.first_name,
            "athlete_last_name": self.athlete.last_name,
            "athlete_full_name": self.athlete.full_name,
            "athlete_nationality": self.athlete.nationality,
            "athlete_birth_year": self.athlete.birth_year,
            "athlete_category": self.athlete.category,
            "athlete_team": self.athlete.team,
            "bib": self.bib,
            "rank": self.rank,
            "status": self.status.value,
            "time_raw": self.time_raw,
            "time_seconds": self.time_seconds,
            "gap_raw": self.gap_raw,
            "gap_seconds": self.gap_seconds,
            "penalty_seconds": self.penalty_seconds,
            "penalty_reason": self.penalty_reason,
            "points": self.points,
        }
        for i, split in enumerate(self.splits, 1):
            flat[f"split_{i}_name"] = split.name
            flat[f"split_{i}_time_raw"] = split.time_raw
            flat[f"split_{i}_time_seconds"] = split.time_seconds
            flat[f"split_{i}_rank"] = split.rank

        return flat


class Event(BaseModel):
    """
    A Ski Mountaineering event (competition) with one or more races.

    Events are typically multi-day competitions held at a single venue,
    containing multiple race formats (e.g., Sprint on Saturday, Individual on Sunday).
    """

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(..., description="Unique event identifier")
    name: str = Field(..., description="Event name")
    location: str | None = Field(None, description="Venue location")
    country: str | None = Field(
        None, min_length=2, max_length=3, description="Host country ISO code"
    )
    start_date: str | None = Field(None, description="Event start date (YYYY-MM-DD)")
    end_date: str | None = Field(None, description="Event end date (YYYY-MM-DD)")
    season: str | None = Field(None, description="Competition season (e.g., '2023-2024')")
    competition_type: str | None = Field(
        None, description="Type (World Cup, World Championship, etc.)"
    )
    races: list[str] = Field(default_factory=list, description="Race IDs within this event")
    url: str | None = Field(None, description="Source URL for event details")

    @field_validator("country", mode="before")
    @classmethod
    def normalize_country(cls, v: Any) -> str | None:
        if v is None or v == "":
            return None
        return str(v).strip().upper()


class SeasonCalendar(BaseModel):
    """Calendar of events for a competition season."""

    model_config = ConfigDict(extra="forbid")

    season: str = Field(..., description="Season identifier (e.g., '2023-2024')")
    events: list[Event] = Field(default_factory=list, description="Events in the season")

    def to_dataframe_records(self) -> list[dict[str, Any]]:
        """Convert calendar to list of dicts for DataFrame conversion."""
        return [
            {
                "event_id": e.event_id,
                "name": e.name,
                "location": e.location,
                "country": e.country,
                "start_date": e.start_date,
                "end_date": e.end_date,
                "season": e.season,
                "competition_type": e.competition_type,
                "url": e.url,
            }
            for e in self.events
        ]
