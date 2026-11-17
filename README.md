# pyskimo

A Python package for fetching, parsing, and analyzing Ski Mountaineering (Skimo) race results.

[![CI](https://github.com/annweng/pyskimo/actions/workflows/ci.yml/badge.svg)](https://github.com/annweng/pyskimo/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pyskimo.svg)](https://pypi.org/project/pyskimo/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

`pyskimo` is a production-grade data ingestion package modeled after [pybaseball](https://github.com/jldbc/pybaseball) that fetches, parses, validates, and caches official Ski Mountaineering race results into clean `pandas` DataFrames.

### Features

- **Multiple Data Sources**: Fetches from ISMF (ismf-ski.com) and DataSkimo (dataskimo.org)
- **Format Support**: Parses both HTML result tables and official PDF result sheets
- **Race Formats**: Handles Sprint, Vertical, Individual, Mixed Relay, and Long Distance events
- **Smart Caching**: Local disk caching via `requests-cache` with configurable TTL
- **Polite Scraping**: Built-in rate limiting and descriptive User-Agent
- **Data Validation**: Pydantic models ensure data quality before DataFrame conversion
- **Status Handling**: Proper handling of DNF, DNS, DSQ, OTL, and LAP statuses
- **Time Parsing**: Converts various time formats to standardized seconds/timedelta

## Installation

```bash
pip install pyskimo
```

Or from source:

```bash
git clone https://github.com/annweng/pyskimo.git
cd pyskimo
pip install -e .

# With development dependencies
pip install -e ".[dev]"
```

## Quick Start

The most reliable way to fetch results is with a **direct URL**:

```python
import pyskimo

# DataSkimo race results (server-rendered HTML — best source for parsing)
df = pyskimo.get_race_results(
    url="https://dataskimo.org/result.php?race=884&id=742"
)

# DataSkimo homepage (latest results)
df = pyskimo.get_race_results(url="https://dataskimo.org/")

# ISMF results hub
df = pyskimo.get_race_results(url="https://ismf-ski.com/results/")

# Season calendar (ISMF)
calendar = pyskimo.get_season_calendar(source="ismf")

# Search for an athlete
athlete_results = pyskimo.search_athlete("Kilian Jornet", nationality="ESP")
```

### Useful site URLs

| What | URL |
|------|-----|
| ISMF results | https://ismf-ski.com/results/ |
| ISMF calendar | https://ismf-ski.com/events-results/calendar |
| ISMF athletes | https://ismf-ski.com/community/athletes/ |
| ISMF event page | https://ismf-ski.com/events/{slug}/ |
| DataSkimo home | https://dataskimo.org/ |
| DataSkimo race | https://dataskimo.org/result.php?race={race}&id={id} |

> **Note:** Parts of the ISMF site are JavaScript-rendered. For those pages, prefer a direct DataSkimo result URL or an ISMF PDF result sheet. Pass the PDF URL to `get_race_results(url=...)` and the PDF parser will handle it.

## DataFrame Output

Results are returned as tidy pandas DataFrames with normalized columns:

| Column | Type | Description |
|--------|------|-------------|
| `rank` | int | Finishing position |
| `bib` | str | Race bib number |
| `athlete_full_name` | str | Athlete's full name |
| `athlete_nationality` | str | ISO country code |
| `athlete_category` | str | Age/gender category |
| `status` | str | finished, dnf, dns, dsq, etc. |
| `time_raw` | str | Original time string |
| `time_seconds` | float | Time in seconds |
| `gap_seconds` | float | Gap to leader in seconds |
| `penalty_seconds` | float | Time penalties applied |

Additional split columns (`split_1_time_seconds`, etc.) are included when intermediate timing data is available.

## Configuration

### Caching

```python
from pyskimo.client import SkimoClient

# Custom cache settings
client = SkimoClient(
    cache_path="~/.my_cache/skimo",  # Custom cache location
    cache_ttl=86400,                  # 24 hour cache TTL
    use_cache=True,                   # Enable/disable caching
)

# Bypass cache for a single request
df = pyskimo.get_race_results(url="...", bypass_cache=True)
```

### Rate Limiting

```python
# Configure rate limiting
client = SkimoClient(
    rate_limit_delay=2.0,  # 2 seconds between requests
    timeout=60.0,          # 60 second timeout
    max_retries=5,         # 5 retry attempts
)
```

## Data Sources

### ISMF (ismf-ski.com)

The International Ski Mountaineering Federation official results portal. Contains:
- World Cup results
- World Championship results
- Continental Championships

Key pages: `/results/`, `/events-results/calendar`, `/community/athletes/`, `/events/{slug}/`

### DataSkimo (dataskimo.org)

Community-maintained database with broader coverage including:
- National championships
- Regional races
- Historical results

Key pages: `/`, `/result.php?race=...&id=...`, `/calendar.php`

## Supported Race Formats

| Format | Description |
|--------|-------------|
| `sprint` | Short, intense races with heats |
| `vertical` | Uphill-only races |
| `individual` | Traditional ski mountaineering races |
| `mixed_relay` | Team relay events |
| `team` | Two-person team races |
| `long_distance` | Extended distance events |

## API Reference

### Main Functions

#### `get_race_results()`

Fetch race results as a DataFrame.

```python
get_race_results(
    url: str | None = None,           # Direct URL to results (preferred)
    event_id: str | None = None,      # Event identifier
    race_id: str | None = None,       # Race within event
    year: int | None = None,          # Year of event
    race_format: str = "unknown",     # Race format type
    source: str = "auto",             # "ismf", "dataskimo", or "auto"
    bypass_cache: bool = False,       # Skip cache for this request
) -> pd.DataFrame
```

#### `get_season_calendar()`

Fetch season calendar of events.

```python
get_season_calendar(
    season: str | None = None,        # e.g., "2023-2024"
    year: int | None = None,          # Starting year
    competition_type: str | None = None,
    source: str = "auto",             # Prefer "ismf" for official calendar
) -> pd.DataFrame
```

#### `get_event_details()`

Fetch details for a specific event.

```python
get_event_details(
    event_id: str,                    # e.g., "ismf-villars-sur-ollon-world-cup"
    year: int | None = None,
    source: str = "auto",
) -> Event | None
```

#### `search_athlete()`

Search for athlete results.

```python
search_athlete(
    name: str,                        # Athlete name (partial match)
    nationality: str | None = None,   # Filter by nationality
    season: str | None = None,        # Limit to season
) -> pd.DataFrame
```

### Schema Classes

- `RaceResult`: Individual race result with validation
- `Athlete`: Athlete identity and demographics
- `Event`: Competition event details
- `Split`: Intermediate timing split
- `RaceFormat`: Enum of race format types
- `ResultStatus`: Enum of result statuses (FINISHED, DNF, DNS, DSQ, etc.)

## Development

### Setup

```bash
git clone https://github.com/annweng/pyskimo.git
cd pyskimo
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src/pyskimo --cov-report=term-missing

# Run specific test file
pytest tests/test_utils.py -v
```

### Linting and Type Checking

```bash
# Run ruff linter
ruff check src tests

# Run ruff formatter
ruff format src tests

# Run mypy type checker
mypy src
```

## Project Structure

```
pyskimo/
├── pyproject.toml          # Package configuration
├── README.md               # This file
├── .github/
│   └── workflows/
│       └── ci.yml          # CI/CD pipeline
├── src/
│   └── pyskimo/
│       ├── __init__.py     # Public API exports
│       ├── client.py       # HTTP client with caching
│       ├── schemas.py      # Pydantic data models
│       ├── results.py      # Main API functions
│       ├── utils.py        # Time parsing utilities
│       └── parsers/
│           ├── html_parser.py  # HTML table extraction
│           └── pdf_parser.py   # PDF result extraction
└── tests/
    ├── fixtures/           # Test data files
    ├── test_utils.py       # Utility function tests
    ├── test_parsers.py     # Parser tests
    └── test_schemas.py     # Schema validation tests
```

## Contributing

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass and linting is clean
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) for details.

## Acknowledgments

- Inspired by [pybaseball](https://github.com/jldbc/pybaseball)
- Data sourced from [ISMF](https://ismf-ski.com) and [DataSkimo](https://dataskimo.org)
- Built for the ski mountaineering community
