"""
HTML parser for extracting Skimo race results from web pages.

This module handles parsing of HTML result tables from:
- ISMF official results portal (ismf-ski.com)
- DataSkimo (dataskimo.org)

The parser handles various table formats and layouts used across these sources.
"""

from __future__ import annotations

import contextlib
import logging
import re
from typing import ClassVar

from bs4 import BeautifulSoup, Tag

from pyskimo.schemas import (
    Athlete,
    Event,
    RaceFormat,
    RaceResult,
    ResultStatus,
    Split,
)
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
)

logger = logging.getLogger(__name__)


class HTMLResultParser:
    """
    Parser for extracting race results from HTML pages.

    This parser handles the complexity of various HTML table formats used
    by ISMF and DataSkimo, including:
    - Standard result tables with rank, name, time columns
    - Tables with intermediate splits
    - Various column naming conventions
    """

    COLUMN_MAPPINGS: ClassVar[dict[str, list[str]]] = {
        "rank": ["rank", "pos", "position", "#", "place", "pl", "rk"],
        "bib": ["bib", "no", "number", "nr", "dorsal"],
        "name": [
            "name",
            "athlete",
            "athete",
            "competitor",
            "rider",
        ],  # note: dataskimo has typo "athete"
        "first_name": ["first_name", "firstname", "first", "given_name"],
        "last_name": ["last_name", "lastname", "last", "surname", "family_name"],
        "nationality": ["nationality", "nat", "nation", "country", "naz"],
        "category": ["category", "cat", "class", "age_group", "group"],
        "team": ["team", "club", "squad"],
        "time": [
            "time",
            "total time",
            "total_time",
            "finish",
            "result",
            "total",
            "finish_time",
        ],
        "gap": ["gap", "diff", "behind", "delta", "+/-"],
        "status": ["status", "state"],
        "points": ["points", "pts", "score", "wc pts", "wc_pts", "wrk pts", "wrk_pts"],
        "year": ["year", "birth_year", "yob"],
        "ismf_id": ["ismf id", "ismf_id", "id", "athlete_id"],
    }

    def __init__(
        self,
        event_id: str | None = None,
        race_id: str | None = None,
        race_format: RaceFormat = RaceFormat.UNKNOWN,
    ) -> None:
        """
        Initialize the HTML parser.

        Args:
            event_id: Optional event identifier to attach to results
            race_id: Optional race identifier to attach to results
            race_format: Race format type
        """
        self.event_id = event_id
        self.race_id = race_id
        self.race_format = race_format

    def parse(self, html: str) -> list[RaceResult]:
        """
        Parse HTML content and extract race results.

        Args:
            html: HTML content as string

        Returns:
            List of validated RaceResult objects
        """
        soup = BeautifulSoup(html, "lxml")

        results: list[RaceResult] = []

        tables = self._find_result_tables(soup)

        for table in tables:
            table_results = self._parse_table(table)
            results.extend(table_results)

        if not results:
            results = self._try_alternative_parsing(soup)

        return results

    def _find_result_tables(self, soup: BeautifulSoup) -> list[Tag]:
        """Find tables that likely contain race results."""
        tables: list[Tag] = []

        result_tables = soup.find_all("table", class_=re.compile(r"result|ranking|standings", re.I))
        tables.extend([t for t in result_tables if isinstance(t, Tag)])

        for table in soup.find_all("table"):
            if not isinstance(table, Tag):
                continue
            if table in tables:
                continue
            headers = self._get_table_headers(table)
            if self._looks_like_results_table(headers):
                tables.append(table)

        return tables

    def _get_table_headers(self, table: Tag) -> list[str]:
        """Extract header names from a table."""
        headers: list[str] = []

        thead = table.find("thead")
        if thead and isinstance(thead, Tag):
            header_row = thead.find("tr")
            if header_row and isinstance(header_row, Tag):
                for th in header_row.find_all(["th", "td"]):
                    text = th.get_text(strip=True).lower()
                    headers.append(text)
                return headers

        first_row = table.find("tr")
        if first_row and isinstance(first_row, Tag):
            cells = first_row.find_all(["th", "td"])
            for cell in cells:
                text = cell.get_text(strip=True).lower()
                headers.append(text)

        return headers

    def _looks_like_results_table(self, headers: list[str]) -> bool:
        """Check if headers suggest this is a results table."""
        required_indicators = ["rank", "pos", "position", "name", "athlete", "time", "result"]
        header_text = " ".join(headers)
        return any(ind in header_text for ind in required_indicators)

    def _parse_table(self, table: Tag) -> list[RaceResult]:
        """Parse a single results table."""
        headers = self._get_table_headers(table)
        column_map = self._map_columns(headers)

        results: list[RaceResult] = []

        tbody = table.find("tbody")
        rows_container = tbody if tbody and isinstance(tbody, Tag) else table

        for row in rows_container.find_all("tr"):
            if not isinstance(row, Tag):
                continue

            if row.find("th"):
                continue

            cells = row.find_all("td")
            if not cells:
                continue

            try:
                result = self._parse_row(cells, column_map, headers)
                if result:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Failed to parse row: {e}")
                continue

        return results

    def _map_columns(self, headers: list[str]) -> dict[str, int]:
        """Map semantic column names to their indices."""
        column_map: dict[str, int] = {}

        for semantic_name, patterns in self.COLUMN_MAPPINGS.items():
            for idx, header in enumerate(headers):
                header_lower = header.lower().strip()
                if any(p in header_lower for p in patterns):
                    if semantic_name not in column_map:
                        column_map[semantic_name] = idx
                    break

        return column_map

    def _parse_row(
        self,
        cells: list[Tag],
        column_map: dict[str, int],
        headers: list[str],
    ) -> RaceResult | None:
        """Parse a single table row into a RaceResult."""

        def get_cell_text(semantic_name: str) -> str | None:
            idx = column_map.get(semantic_name)
            if idx is not None and idx < len(cells):
                return cells[idx].get_text(strip=True)
            return None

        def get_cell_nationality(semantic_name: str) -> str | None:
            """Extract nationality, handling both text and flag image formats."""
            idx = column_map.get(semantic_name)
            if idx is None or idx >= len(cells):
                return None
            cell = cells[idx]
            text = cell.get_text(strip=True)
            if text:
                cleaned = text.strip("()")
                if len(cleaned) in (2, 3) and cleaned.isalpha():
                    return cleaned.upper()
            img = cell.find("img")
            if img and isinstance(img, Tag):
                src = img.get("src", "")
                alt = img.get("alt", "")
                if alt and len(str(alt)) in (2, 3):
                    return str(alt).upper()
                if src:
                    match = re.search(r"/([A-Z]{2,3})\.png", str(src), re.I)
                    if match:
                        return match.group(1).upper()
            return None

        name_text = get_cell_text("name")
        first_name = get_cell_text("first_name")
        last_name = get_cell_text("last_name")

        if not name_text and not (first_name and last_name):
            return None

        if name_text:
            name_text, extracted_nat = extract_nationality_from_name(name_text)
        else:
            extracted_nat = None

        if first_name and last_name:
            full_name = f"{first_name} {last_name}"
        else:
            full_name = normalize_name(name_text) or name_text or ""

        if not full_name.strip():
            return None

        nationality = get_cell_nationality("nationality") or extracted_nat

        year_str = get_cell_text("year")
        birth_year = None
        if year_str:
            with contextlib.suppress(ValueError):
                birth_year = int(year_str)
                if birth_year < 1900 or birth_year > 2020:
                    birth_year = None

        athlete_id = get_cell_text("ismf_id")

        athlete = Athlete(
            athlete_id=athlete_id,
            full_name=full_name,
            first_name=first_name,
            last_name=last_name,
            nationality=nationality,
            birth_year=birth_year,
            category=get_cell_text("category"),
            team=get_cell_text("team"),
        )

        rank_str = get_cell_text("rank")
        rank = parse_rank(rank_str)

        time_str = get_cell_text("time")
        status_str = get_cell_text("status")

        if status_str and is_status_code(status_str):
            status_code = parse_status_code(status_str)
        elif time_str and is_status_code(time_str):
            status_code = parse_status_code(time_str)
            time_str = None
        else:
            status_code = None

        status = ResultStatus.FINISHED
        if status_code:
            status_map = {
                "DNF": ResultStatus.DNF,
                "DNS": ResultStatus.DNS,
                "DSQ": ResultStatus.DSQ,
                "LAP": ResultStatus.LAP,
                "OTL": ResultStatus.OTL,
            }
            status = status_map.get(status_code, ResultStatus.DNF)

        time_seconds = parse_time_to_seconds(time_str)
        time_delta = parse_time_to_timedelta(time_str)

        gap_str = get_cell_text("gap")
        gap_seconds = parse_gap_time(gap_str)

        bib = parse_bib_number(get_cell_text("bib"))

        points_str = get_cell_text("points")
        points = None
        if points_str:
            with contextlib.suppress(ValueError):
                points = float(points_str.replace(",", "."))

        splits = self._extract_splits(cells, column_map, headers)

        return RaceResult(
            event_id=self.event_id,
            race_id=self.race_id,
            race_format=self.race_format,
            athlete=athlete,
            bib=bib,
            rank=rank,
            status=status,
            time_raw=time_str,
            time_seconds=time_seconds,
            time_delta=time_delta,
            gap_raw=gap_str,
            gap_seconds=gap_seconds,
            splits=splits,
            points=points,
        )

    def _extract_splits(
        self,
        cells: list[Tag],
        column_map: dict[str, int],
        headers: list[str],
    ) -> list[Split]:
        """Extract intermediate split times from row."""
        splits: list[Split] = []
        mapped_indices = set(column_map.values())

        split_patterns = re.compile(
            r"(split|intermediate|t\d+|transition|climb|descent|s\d+)", re.I
        )

        for idx, header in enumerate(headers):
            if idx in mapped_indices:
                continue
            if idx >= len(cells):
                continue

            if split_patterns.search(header):
                time_str = cells[idx].get_text(strip=True)
                time_seconds = parse_time_to_seconds(time_str)

                if time_str or time_seconds is not None:
                    splits.append(
                        Split(
                            name=header,
                            time_raw=time_str if time_str else None,
                            time_seconds=time_seconds,
                        )
                    )

        return splits

    def _try_alternative_parsing(self, soup: BeautifulSoup) -> list[RaceResult]:
        """Try alternative parsing strategies when standard table parsing fails."""
        results: list[RaceResult] = []

        result_divs = soup.find_all("div", class_=re.compile(r"result|athlete|competitor", re.I))

        for div in result_divs:
            if not isinstance(div, Tag):
                continue
            try:
                result = self._parse_result_div(div)
                if result:
                    results.append(result)
            except Exception as e:
                logger.debug(f"Failed to parse div: {e}")
                continue

        return results

    def _parse_result_div(self, div: Tag) -> RaceResult | None:
        """Parse a result from a div-based layout."""
        name_elem = div.find(class_=re.compile(r"name|athlete", re.I))
        if not name_elem:
            return None

        full_name = name_elem.get_text(strip=True)
        if not full_name:
            return None

        full_name, nationality = extract_nationality_from_name(full_name)
        full_name = normalize_name(full_name) or full_name

        rank_elem = div.find(class_=re.compile(r"rank|position|pos", re.I))
        rank = parse_rank(rank_elem.get_text(strip=True)) if rank_elem else None

        time_elem = div.find(class_=re.compile(r"time|result|finish", re.I))
        time_str = time_elem.get_text(strip=True) if time_elem else None

        nat_elem = div.find(class_=re.compile(r"nationality|country|nat", re.I))
        if nat_elem:
            nationality = nat_elem.get_text(strip=True)

        athlete = Athlete(
            full_name=full_name,
            nationality=nationality,
        )

        status = ResultStatus.FINISHED
        if time_str and is_status_code(time_str):
            status_code = parse_status_code(time_str)
            if status_code == "DNF":
                status = ResultStatus.DNF
            elif status_code == "DNS":
                status = ResultStatus.DNS
            elif status_code == "DSQ":
                status = ResultStatus.DSQ
            time_str = None

        return RaceResult(
            event_id=self.event_id,
            race_id=self.race_id,
            race_format=self.race_format,
            athlete=athlete,
            rank=rank,
            status=status,
            time_raw=time_str,
            time_seconds=parse_time_to_seconds(time_str),
            time_delta=parse_time_to_timedelta(time_str),
        )


def parse_results_html(
    html: str,
    event_id: str | None = None,
    race_id: str | None = None,
    race_format: RaceFormat = RaceFormat.UNKNOWN,
) -> list[RaceResult]:
    """
    Parse race results from HTML content.

    Args:
        html: HTML content as string
        event_id: Optional event identifier
        race_id: Optional race identifier
        race_format: Race format type

    Returns:
        List of validated RaceResult objects
    """
    parser = HTMLResultParser(
        event_id=event_id,
        race_id=race_id,
        race_format=race_format,
    )
    return parser.parse(html)


def parse_event_html(html: str) -> Event | None:
    """
    Parse event details from an HTML page.

    Args:
        html: HTML content as string

    Returns:
        Event object or None if parsing fails
    """
    soup = BeautifulSoup(html, "lxml")

    title_elem = soup.find("h1") or soup.find("title")
    if not title_elem:
        return None

    name = title_elem.get_text(strip=True)

    event_id = ""
    meta_id = soup.find("meta", {"name": "event-id"})
    if meta_id and isinstance(meta_id, Tag):
        event_id = str(meta_id.get("content", ""))

    location = None
    location_elem = soup.find(class_=re.compile(r"location|venue", re.I))
    if location_elem:
        location = location_elem.get_text(strip=True)

    country = None
    country_elem = soup.find(class_=re.compile(r"country|nation", re.I))
    if country_elem:
        country = country_elem.get_text(strip=True)

    return Event(
        event_id=event_id or name.replace(" ", "_").lower(),
        name=name,
        location=location,
        country=country,
    )


def parse_calendar_html(html: str, season: str | None = None) -> list[Event]:
    """
    Parse a season calendar from HTML content.

    Args:
        html: HTML content as string
        season: Optional season identifier

    Returns:
        List of Event objects
    """
    soup = BeautifulSoup(html, "lxml")
    events: list[Event] = []

    event_rows = soup.find_all("tr", class_=re.compile(r"event|race|competition", re.I))
    if not event_rows:
        event_rows = soup.find_all("div", class_=re.compile(r"event|race|competition", re.I))

    for idx, row in enumerate(event_rows):
        if not isinstance(row, Tag):
            continue

        name_elem = row.find(class_=re.compile(r"name|title|event", re.I))
        if not name_elem:
            cells = row.find_all("td")
            if len(cells) >= 2:
                name_elem = cells[1]

        if not name_elem:
            continue

        name = name_elem.get_text(strip=True)
        if not name:
            continue

        date_elem = row.find(class_=re.compile(r"date|when", re.I))
        date_str = date_elem.get_text(strip=True) if date_elem else None

        location_elem = row.find(class_=re.compile(r"location|venue|where", re.I))
        location = location_elem.get_text(strip=True) if location_elem else None

        country_elem = row.find(class_=re.compile(r"country|nation", re.I))
        country = country_elem.get_text(strip=True) if country_elem else None

        link = row.find("a", href=True)
        url = None
        if link and isinstance(link, Tag):
            url = str(link.get("href", ""))

        events.append(
            Event(
                event_id=f"event_{idx + 1}",
                name=name,
                location=location,
                country=country,
                start_date=date_str,
                season=season,
                url=url,
            )
        )

    return events
