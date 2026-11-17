"""
pyskimo - A Python package for fetching and analyzing Ski Mountaineering race results.

This package provides tools for:
- Fetching race results from ISMF and DataSkimo portals
- Parsing HTML result tables and official PDF result sheets
- Converting race times to standardized formats
- Validating and normalizing race data into pandas DataFrames

Example usage:
    >>> import pyskimo
    >>> # Get race results as a DataFrame
    >>> df = pyskimo.get_race_results(event_id="12345", year=2024)
    >>> # Get season calendar
    >>> calendar = pyskimo.get_season_calendar(season="2023-2024")
"""

from pyskimo.results import (
    get_event_details,
    get_race_results,
    get_season_calendar,
    search_athlete,
)
from pyskimo.schemas import (
    Athlete,
    Event,
    RaceFormat,
    RaceResult,
    ResultStatus,
    Split,
)

__version__ = "0.1.0"
__all__ = [
    "Athlete",
    "Event",
    "RaceFormat",
    "RaceResult",
    "ResultStatus",
    "Split",
    "__version__",
    "get_event_details",
    "get_race_results",
    "get_season_calendar",
    "search_athlete",
]
