# pyskimo

A Python package for fetching, parsing, and analyzing Ski Mountaineering (Skimo) race results.

[![CI](https://github.com/pyskimo/pyskimo/actions/workflows/ci.yml/badge.svg)](https://github.com/pyskimo/pyskimo/actions/workflows/ci.yml)
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
# Install from source
git clone https://github.com/pyskimo/pyskimo.git
cd pyskimo
pip install -e .

# Or with development dependencies
pip install -e ".[dev]"
```

## Quick Start

```python
import pyskimo

# Fetch race results by direct URL
df = pyskimo.get_race_results(
    url="https://ismf-ski.com/results/2024/world-cup-sprint"
)

# Fetch results by event ID
df = pyskimo.get_race_results(
    event_id="wc-andorra-2024",
    race_id="sprint-men",
    race_format="sprint"
)

# Get season calendar
calendar = pyskimo.get_season_calendar(season="2023-2024")

# Search for athlete results
athlete_results = pyskimo.search_athlete("Kilian Jornet", nationality="ESP")
```

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

### DataSkimo (dataskimo.org)

Community-maintained database with broader coverage including:
- National championships
- Regional races
- Historical results

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
    url: str | None = None,           # Direct URL to results
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
    source: str = "auto",
) -> pd.DataFrame
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
# Clone and install
git clone https://github.com/pyskimo/pyskimo.git
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
