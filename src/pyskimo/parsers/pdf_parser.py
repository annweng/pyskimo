"""
PDF parser for extracting Skimo race results from official result sheets.

This module handles parsing of official PDF result documents, commonly used
for detailed split times and official race certifications. Supports various
race formats including Sprint, Vertical, Individual, and Mixed Relay.
"""

from __future__ import annotations

import contextlib
import io
import logging
import re
from pathlib import Path
from typing import Any

import pdfplumber

from pyskimo.schemas import (
    Athlete,
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


class PDFResultParser:
    """
    Parser for extracting race results from official PDF result sheets.

    Handles various PDF formats including:
    - Standard tabular result sheets
    - Multi-page documents
    - Split time sheets with multiple intermediate points
    """

    def __init__(
        self,
        event_id: str | None = None,
        race_id: str | None = None,
        race_format: RaceFormat = RaceFormat.UNKNOWN,
    ) -> None:
        """
        Initialize the PDF parser.

        Args:
            event_id: Optional event identifier to attach to results
            race_id: Optional race identifier to attach to results
            race_format: Race format type
        """
        self.event_id = event_id
        self.race_id = race_id
        self.race_format = race_format

    def parse(self, pdf_content: bytes | Path | str) -> list[RaceResult]:
        """
        Parse PDF content and extract race results.

        Args:
            pdf_content: PDF as bytes, file path, or path string

        Returns:
            List of validated RaceResult objects
        """
        if isinstance(pdf_content, (str, Path)):
            pdf_path = Path(pdf_content)
            pdf_file: Any = pdf_path
        else:
            pdf_file = io.BytesIO(pdf_content)

        results: list[RaceResult] = []

        with pdfplumber.open(pdf_file) as pdf:
            all_tables: list[list[list[str | None]]] = []

            for page in pdf.pages:
                tables = page.extract_tables()
                all_tables.extend(tables)

            if all_tables:
                results = self._parse_tables(all_tables)

            if not results:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"

                if text.strip():
                    results = self._parse_text(text)

        return results

    def _parse_tables(
        self,
        tables: list[list[list[str | None]]],
    ) -> list[RaceResult]:
        """Parse extracted tables from PDF."""
        results: list[RaceResult] = []

        for table in tables:
            if not table or len(table) < 2:
                continue

            headers = self._extract_headers(table[0])
            if not self._is_results_table(headers):
                continue

            column_map = self._map_columns(headers)

            for row in table[1:]:
                try:
                    result = self._parse_row(row, column_map, headers)
                    if result:
                        results.append(result)
                except Exception as e:
                    logger.debug(f"Failed to parse PDF row: {e}")
                    continue

        return results

    def _extract_headers(self, header_row: list[str | None]) -> list[str]:
        """Clean and normalize header row."""
        return [str(h).strip().lower() if h else "" for h in header_row]

    def _is_results_table(self, headers: list[str]) -> bool:
        """Check if headers indicate a results table."""
        result_indicators = ["rank", "pos", "name", "athlete", "time", "result", "bib"]
        header_text = " ".join(headers)
        return any(ind in header_text for ind in result_indicators)

    def _map_columns(self, headers: list[str]) -> dict[str, int]:
        """Map column names to indices."""
        mappings = {
            "rank": ["rank", "pos", "position", "pl", "rk", "#"],
            "bib": ["bib", "no", "number", "nr", "dorsal"],
            "name": ["name", "athlete", "competitor"],
            "first_name": ["first", "firstname", "first_name", "given"],
            "last_name": ["last", "lastname", "last_name", "surname", "family"],
            "nationality": ["nat", "nationality", "country", "nation"],
            "category": ["cat", "category", "class", "group"],
            "team": ["team", "club"],
            "time": ["time", "finish", "result", "total"],
            "gap": ["gap", "diff", "behind", "+/-"],
            "status": ["status", "state"],
            "points": ["points", "pts"],
        }

        column_map: dict[str, int] = {}

        for semantic, patterns in mappings.items():
            for idx, header in enumerate(headers):
                if any(p in header for p in patterns):
                    if semantic not in column_map:
                        column_map[semantic] = idx
                    break

        return column_map

    def _parse_row(
        self,
        row: list[str | None],
        column_map: dict[str, int],
        headers: list[str],
    ) -> RaceResult | None:
        """Parse a single table row."""

        def get_cell(name: str) -> str | None:
            idx = column_map.get(name)
            if idx is not None and idx < len(row):
                val = row[idx]
                return str(val).strip() if val else None
            return None

        name = get_cell("name")
        first_name = get_cell("first_name")
        last_name = get_cell("last_name")

        if not name and not (first_name and last_name):
            return None

        if name:
            name, extracted_nat = extract_nationality_from_name(name)
        else:
            extracted_nat = None

        if first_name and last_name:
            full_name = f"{first_name} {last_name}"
        else:
            full_name = normalize_name(name) or name or ""

        if not full_name.strip():
            return None

        nationality = get_cell("nationality") or extracted_nat

        athlete = Athlete(
            full_name=full_name,
            first_name=first_name,
            last_name=last_name,
            nationality=nationality,
            category=get_cell("category"),
            team=get_cell("team"),
        )

        rank = parse_rank(get_cell("rank"))
        bib = parse_bib_number(get_cell("bib"))

        time_str = get_cell("time")
        status_str = get_cell("status")

        status = ResultStatus.FINISHED
        if status_str and is_status_code(status_str):
            status_code = parse_status_code(status_str)
        elif time_str and is_status_code(time_str):
            status_code = parse_status_code(time_str)
            time_str = None
        else:
            status_code = None

        if status_code:
            status_map = {
                "DNF": ResultStatus.DNF,
                "DNS": ResultStatus.DNS,
                "DSQ": ResultStatus.DSQ,
                "LAP": ResultStatus.LAP,
                "OTL": ResultStatus.OTL,
            }
            status = status_map.get(status_code, ResultStatus.DNF)

        gap_str = get_cell("gap")

        points_str = get_cell("points")
        points = None
        if points_str:
            with contextlib.suppress(ValueError):
                points = float(points_str.replace(",", "."))

        splits = self._extract_splits(row, column_map, headers)

        return RaceResult(
            event_id=self.event_id,
            race_id=self.race_id,
            race_format=self.race_format,
            athlete=athlete,
            bib=bib,
            rank=rank,
            status=status,
            time_raw=time_str,
            time_seconds=parse_time_to_seconds(time_str),
            time_delta=parse_time_to_timedelta(time_str),
            gap_raw=gap_str,
            gap_seconds=parse_gap_time(gap_str),
            splits=splits,
            points=points,
        )

    def _extract_splits(
        self,
        row: list[str | None],
        column_map: dict[str, int],
        headers: list[str],
    ) -> list[Split]:
        """Extract split times from row."""
        splits: list[Split] = []
        mapped_indices = set(column_map.values())

        split_pattern = re.compile(r"(split|intermediate|t\d|trans|climb|desc|s\d)", re.I)

        for idx, header in enumerate(headers):
            if idx in mapped_indices:
                continue
            if idx >= len(row):
                continue

            if split_pattern.search(header):
                val = row[idx]
                time_str = str(val).strip() if val else None
                time_seconds = parse_time_to_seconds(time_str)

                if time_str or time_seconds is not None:
                    splits.append(
                        Split(
                            name=header,
                            time_raw=time_str,
                            time_seconds=time_seconds,
                        )
                    )

        return splits

    def _parse_text(self, text: str) -> list[RaceResult]:
        """
        Fallback parser for PDFs without extractable tables.

        Uses regex patterns to identify result lines.
        """
        results: list[RaceResult] = []

        result_pattern = re.compile(
            r"^\s*"
            r"(?P<rank>\d+)\s+"
            r"(?:(?P<bib>\d+)\s+)?"
            r"(?P<name>[A-Za-z\s,\-']+?)"
            r"(?:\s+\((?P<nat>[A-Z]{2,3})\))?"
            r"\s+"
            r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?(?:\.\d+)?|DNF|DNS|DSQ)"
            r"(?:\s+(?P<gap>[+\-]?\d{1,2}:\d{2}(?:\.\d+)?))?"
            r"\s*$",
            re.MULTILINE,
        )

        for match in result_pattern.finditer(text):
            groups = match.groupdict()

            name = groups.get("name", "").strip()
            if not name:
                continue

            name = normalize_name(name) or name
            nationality = groups.get("nat")

            athlete = Athlete(
                full_name=name,
                nationality=nationality,
            )

            rank = parse_rank(groups.get("rank"))
            bib = parse_bib_number(groups.get("bib"))

            time_str = groups.get("time")
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

            gap_str = groups.get("gap")

            results.append(
                RaceResult(
                    event_id=self.event_id,
                    race_id=self.race_id,
                    race_format=self.race_format,
                    athlete=athlete,
                    bib=bib,
                    rank=rank,
                    status=status,
                    time_raw=time_str,
                    time_seconds=parse_time_to_seconds(time_str),
                    time_delta=parse_time_to_timedelta(time_str),
                    gap_raw=gap_str,
                    gap_seconds=parse_gap_time(gap_str),
                )
            )

        return results


def parse_results_pdf(
    pdf_content: bytes | Path | str,
    event_id: str | None = None,
    race_id: str | None = None,
    race_format: RaceFormat = RaceFormat.UNKNOWN,
) -> list[RaceResult]:
    """
    Parse race results from a PDF document.

    Args:
        pdf_content: PDF as bytes, file path, or path string
        event_id: Optional event identifier
        race_id: Optional race identifier
        race_format: Race format type

    Returns:
        List of validated RaceResult objects
    """
    parser = PDFResultParser(
        event_id=event_id,
        race_id=race_id,
        race_format=race_format,
    )
    return parser.parse(pdf_content)
