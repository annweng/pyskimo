"""
Public API for fetching Skimo race results and event data.

This module provides the main entry points for users of pyskimo:
- get_race_results(): Fetch and parse race results into a DataFrame
- get_season_calendar(): Fetch the season calendar of events
- get_event_details(): Fetch details for a specific event
- search_athlete(): Search for athlete results
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

import pandas as pd

from pyskimo.client import SkimoClient, get_default_client
from pyskimo.parsers.html_parser import (
    HTMLResultParser,
    parse_calendar_html,
    parse_event_html,
)
from pyskimo.parsers.pdf_parser import PDFResultParser
from pyskimo.schemas import Event, RaceFormat, RaceResult

logger = logging.getLogger(__name__)

ISMF_BASE_URL = "https://ismf-ski.com"
DATASKIMO_BASE_URL = "https://dataskimo.org"


def _results_to_dataframe(results: list[RaceResult]) -> pd.DataFrame:
    """Convert list of RaceResult objects to a pandas DataFrame."""
    if not results:
        return pd.DataFrame()  # type: ignore[no-any-return]

    records = [r.to_flat_dict() for r in results]
    df: pd.DataFrame = pd.DataFrame(records)

    expected_columns = [
        "event_id",
        "race_id",
        "race_format",
        "athlete_id",
        "athlete_first_name",
        "athlete_last_name",
        "athlete_full_name",
        "athlete_nationality",
        "athlete_birth_year",
        "athlete_category",
        "athlete_team",
        "bib",
        "rank",
        "status",
        "time_raw",
        "time_seconds",
        "gap_raw",
        "gap_seconds",
        "penalty_seconds",
        "penalty_reason",
        "points",
    ]

    for col in expected_columns:
        if col not in df.columns:
            df[col] = None

    existing_cols = [c for c in expected_columns if c in df.columns]
    extra_cols = [c for c in df.columns if c not in expected_columns]
    df = df[existing_cols + extra_cols]

    return df


def get_race_results(
    url: str | None = None,
    event_id: str | None = None,
    race_id: str | None = None,
    year: int | None = None,
    race_format: RaceFormat | str = RaceFormat.UNKNOWN,
    source: str = "auto",
    client: SkimoClient | None = None,
    bypass_cache: bool = False,
) -> pd.DataFrame:
    """
    Fetch and parse race results into a pandas DataFrame.

    This function supports multiple ways of specifying which results to fetch:
    - Direct URL to a results page
    - Event ID and optional race ID
    - Event ID and year combination

    Args:
        url: Direct URL to results page (HTML or PDF)
        event_id: Event identifier (used if url not provided)
        race_id: Specific race within event (optional)
        year: Year of the event (optional, used with event_id)
        race_format: Type of race (sprint, vertical, etc.)
        source: Data source - "ismf", "dataskimo", or "auto"
        client: Optional SkimoClient instance (uses default if not provided)
        bypass_cache: If True, skip cache for this request

    Returns:
        pandas DataFrame with race results

    Raises:
        ValueError: If neither url nor event_id is provided

    Examples:
        >>> # Fetch by direct URL - ISMF results page
        >>> df = get_race_results(url="https://ismf-ski.com/results/")

        >>> # Fetch by direct URL - DataSkimo specific race
        >>> df = get_race_results(url="https://dataskimo.org/result.php?race=884&id=742")

        >>> # Fetch by direct URL - DataSkimo homepage with latest results
        >>> df = get_race_results(url="https://dataskimo.org/")
    """
    if client is None:
        client = get_default_client()

    if isinstance(race_format, str):
        try:
            race_format = RaceFormat(race_format.lower())
        except ValueError:
            race_format = RaceFormat.UNKNOWN

    if url:
        return _fetch_results_from_url(
            url=url,
            event_id=event_id,
            race_id=race_id,
            race_format=race_format,
            client=client,
            bypass_cache=bypass_cache,
        )

    if event_id:
        return _fetch_results_by_event(
            event_id=event_id,
            race_id=race_id,
            year=year,
            race_format=race_format,
            source=source,
            client=client,
            bypass_cache=bypass_cache,
        )

    raise ValueError("Either 'url' or 'event_id' must be provided")


def _fetch_results_from_url(
    url: str,
    event_id: str | None,
    race_id: str | None,
    race_format: RaceFormat,
    client: SkimoClient,
    bypass_cache: bool,
) -> pd.DataFrame:
    """Fetch and parse results from a direct URL."""
    is_pdf = url.lower().endswith(".pdf")

    if is_pdf:
        content = client.get_bytes(url, bypass_cache=bypass_cache)
        pdf_parser = PDFResultParser(
            event_id=event_id,
            race_id=race_id,
            race_format=race_format,
        )
        results = pdf_parser.parse(content)
    else:
        html = client.get_html(url, bypass_cache=bypass_cache)
        html_parser = HTMLResultParser(
            event_id=event_id,
            race_id=race_id,
            race_format=race_format,
        )
        results = html_parser.parse(html)

    return _results_to_dataframe(results)


def _fetch_results_by_event(
    event_id: str,
    race_id: str | None,
    year: int | None,
    race_format: RaceFormat,
    source: str,
    client: SkimoClient,
    bypass_cache: bool,
) -> pd.DataFrame:
    """Fetch results by event ID from configured data sources."""
    urls_to_try = _build_result_urls(event_id, race_id, year, source)

    for url in urls_to_try:
        try:
            logger.info(f"Attempting to fetch results from: {url}")
            return _fetch_results_from_url(
                url=url,
                event_id=event_id,
                race_id=race_id,
                race_format=race_format,
                client=client,
                bypass_cache=bypass_cache,
            )
        except Exception as e:
            logger.debug(f"Failed to fetch from {url}: {e}")
            continue

    logger.warning(f"No results found for event_id={event_id}, race_id={race_id}, year={year}")
    return pd.DataFrame()  # type: ignore[no-any-return]


def _build_result_urls(
    event_id: str,
    race_id: str | None,
    year: int | None,  # noqa: ARG001 - kept for API compatibility
    source: str,
) -> list[str]:
    """Build list of URLs to try for fetching results."""
    urls: list[str] = []

    if source in ("ismf", "auto"):
        ismf_paths = [
            "/results/",
        ]
        urls.extend(urljoin(ISMF_BASE_URL, p) for p in ismf_paths)

    if source in ("dataskimo", "auto"):
        if race_id:
            dataskimo_paths = [
                f"/result.php?race={event_id}&id={race_id}",
            ]
        else:
            dataskimo_paths = [
                "/index.php",
            ]
        urls.extend(urljoin(DATASKIMO_BASE_URL, p) for p in dataskimo_paths)

    return urls


def get_season_calendar(
    season: str | None = None,
    year: int | None = None,
    competition_type: str | None = None,
    source: str = "auto",
    client: SkimoClient | None = None,
    bypass_cache: bool = False,
) -> pd.DataFrame:
    """
    Fetch the season calendar of Skimo events.

    Args:
        season: Season identifier (e.g., "2023-2024")
        year: Alternative to season - just provide the starting year
        competition_type: Filter by type (e.g., "world_cup", "world_championship")
        source: Data source - "ismf", "dataskimo", or "auto"
        client: Optional SkimoClient instance
        bypass_cache: If True, skip cache for this request

    Returns:
        pandas DataFrame with event calendar

    Examples:
        >>> calendar = get_season_calendar(season="2023-2024")
        >>> calendar = get_season_calendar(year=2023, competition_type="world_cup")
    """
    if client is None:
        client = get_default_client()

    if year and not season:
        season = f"{year}-{year + 1}"

    events: list[Event] = []

    urls = _build_calendar_urls(season, competition_type, source)

    for url in urls:
        try:
            logger.info(f"Fetching calendar from: {url}")
            html = client.get_html(url, bypass_cache=bypass_cache)
            parsed_events = parse_calendar_html(html, season=season)
            events.extend(parsed_events)

            if events:
                break

        except Exception as e:
            logger.debug(f"Failed to fetch calendar from {url}: {e}")
            continue

    if not events:
        return pd.DataFrame()  # type: ignore[no-any-return]

    records: list[dict[str, str | None]] = [
        {
            "event_id": e.event_id,
            "name": e.name,
            "location": e.location,
            "country": e.country,
            "start_date": e.start_date,
            "end_date": e.end_date,
            "season": e.season or season,
            "competition_type": e.competition_type,
            "url": e.url,
        }
        for e in events
    ]

    return pd.DataFrame(records)  # type: ignore[no-any-return]


def _build_calendar_urls(
    season: str | None,
    competition_type: str | None,  # noqa: ARG001 - kept for API compatibility
    source: str,
) -> list[str]:
    """Build URLs for fetching calendar."""
    urls: list[str] = []

    if source in ("ismf", "auto"):
        ismf_paths = [
            "/events-results/calendar",
            "/events-results/",
        ]
        urls.extend(urljoin(ISMF_BASE_URL, p) for p in ismf_paths)

    if source in ("dataskimo", "auto"):
        season_param = f"?season={season}" if season else ""
        dataskimo_paths = [
            f"/calendar.php{season_param}",
            "/index.php",
        ]
        urls.extend(urljoin(DATASKIMO_BASE_URL, p) for p in dataskimo_paths)

    return urls


def get_event_details(
    event_id: str,
    year: int | None = None,
    source: str = "auto",
    client: SkimoClient | None = None,
    bypass_cache: bool = False,
) -> Event | None:
    """
    Fetch details for a specific event.

    Args:
        event_id: Event identifier
        year: Year of the event (optional)
        source: Data source - "ismf", "dataskimo", or "auto"
        client: Optional SkimoClient instance
        bypass_cache: If True, skip cache for this request

    Returns:
        Event object or None if not found

    Examples:
        >>> event = get_event_details("ismf-villars-sur-ollon-world-cup")
    """
    if client is None:
        client = get_default_client()

    # year is kept for API compatibility but not currently used
    _ = year

    urls: list[str] = []

    if source in ("ismf", "auto"):
        urls.extend(
            [
                urljoin(ISMF_BASE_URL, f"/events/{event_id}/"),
            ]
        )

    if source in ("dataskimo", "auto"):
        urls.extend(
            [
                urljoin(DATASKIMO_BASE_URL, f"/calendarEvent.php?id={event_id}"),
            ]
        )

    for url in urls:
        try:
            logger.info(f"Fetching event details from: {url}")
            html = client.get_html(url, bypass_cache=bypass_cache)
            event = parse_event_html(html)

            if event:
                event.url = url
                return event

        except Exception as e:
            logger.debug(f"Failed to fetch event from {url}: {e}")
            continue

    return None


def search_athlete(
    name: str,
    nationality: str | None = None,
    season: str | None = None,
    source: str = "auto",
    client: SkimoClient | None = None,
    bypass_cache: bool = False,
) -> pd.DataFrame:
    """
    Search for an athlete's results.

    Args:
        name: Athlete name (partial match supported)
        nationality: Filter by nationality code (e.g., "ITA", "FRA")
        season: Limit to specific season
        source: Data source - "ismf", "dataskimo", or "auto"
        client: Optional SkimoClient instance
        bypass_cache: If True, skip cache for this request

    Returns:
        pandas DataFrame with athlete's results

    Examples:
        >>> results = search_athlete("Kilian Jornet")
        >>> results = search_athlete("Jornet", nationality="ESP", season="2023-2024")
    """
    if client is None:
        client = get_default_client()

    all_results: list[RaceResult] = []

    urls = _build_athlete_search_urls(name, nationality, season, source)

    for url in urls:
        try:
            logger.info(f"Searching athlete at: {url}")
            html = client.get_html(url, bypass_cache=bypass_cache)
            parser = HTMLResultParser()
            results = parser.parse(html)

            name_lower = name.lower()
            filtered = [r for r in results if name_lower in r.athlete.full_name.lower()]

            if nationality:
                nat_upper = nationality.upper()
                filtered = [
                    r
                    for r in filtered
                    if r.athlete.nationality and r.athlete.nationality.upper() == nat_upper
                ]

            all_results.extend(filtered)

        except Exception as e:
            logger.debug(f"Failed to search at {url}: {e}")
            continue

    return _results_to_dataframe(all_results)


def _build_athlete_search_urls(
    name: str,
    nationality: str | None,
    season: str | None,
    source: str,
) -> list[str]:
    """Build URLs for athlete search."""
    urls: list[str] = []

    name_encoded = name.replace(" ", "+")
    nat_param = f"&nationality={nationality}" if nationality else ""
    season_param = f"&season={season}" if season else ""

    if source in ("ismf", "auto"):
        urls.append(
            urljoin(ISMF_BASE_URL, f"/athletes/search?q={name_encoded}{nat_param}{season_param}")
        )

    if source in ("dataskimo", "auto"):
        urls.append(urljoin(DATASKIMO_BASE_URL, f"/search?athlete={name_encoded}{nat_param}"))

    return urls
