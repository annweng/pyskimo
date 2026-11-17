"""
Utility functions for time parsing, normalization, and data transformation.

This module handles the complexity of parsing race times from various formats
used in Skimo timing systems, including handling of special statuses like
DNF, DNS, DSQ, and time penalties.
"""

from __future__ import annotations

import re
from datetime import timedelta

STATUS_PATTERNS: frozenset[str] = frozenset(
    {
        "dnf",
        "dns",
        "dsq",
        "lap",
        "otl",
        "dq",
        "np",
        "nc",
        "wd",
        "did not finish",
        "did not start",
        "disqualified",
        "lapped",
        "outside time limit",
        "not placed",
        "not classified",
        "withdrawn",
    }
)

TIME_PATTERN_HMS = re.compile(
    r"^"
    r"(?P<sign>[+-])?"
    r"(?:(?P<hours>\d{1,2}):)?"
    r"(?P<minutes>\d{1,2}):"
    r"(?P<seconds>\d{1,2})"
    r"(?:\.(?P<ms>\d{1,3}))?"
    r"$"
)

TIME_PATTERN_MS_ONLY = re.compile(
    r"^"
    r"(?P<sign>[+-])?"
    r"(?P<minutes>\d{1,2}):"
    r"(?P<seconds>\d{1,2})"
    r"(?:\.(?P<ms>\d{1,3}))?"
    r"$"
)

TIME_PATTERN_SECONDS_ONLY = re.compile(
    r"^"
    r"(?P<sign>[+-])?"
    r"(?P<seconds>\d+)"
    r"(?:\.(?P<ms>\d{1,3}))?"
    r"\s*(?:s|sec|seconds?)?"
    r"$",
    re.IGNORECASE,
)


def is_status_code(value: str) -> bool:
    """
    Check if a string represents a non-finish status code.

    Args:
        value: String to check

    Returns:
        True if the string is a recognized status code (DNF, DNS, DSQ, etc.)

    Examples:
        >>> is_status_code("DNF")
        True
        >>> is_status_code("1:23:45")
        False
        >>> is_status_code("Did Not Finish")
        True
    """
    if not value:
        return False
    normalized = value.strip().lower()
    if normalized in STATUS_PATTERNS:
        return True
    return any(pattern in normalized for pattern in STATUS_PATTERNS)


def parse_status_code(value: str) -> str | None:
    """
    Extract the status code from a string.

    Args:
        value: String potentially containing a status code

    Returns:
        Normalized status code (uppercase) or None if not a status

    Examples:
        >>> parse_status_code("DNF")
        'DNF'
        >>> parse_status_code("Did Not Finish")
        'DNF'
        >>> parse_status_code("dsq - equipment")
        'DSQ'
    """
    if not value:
        return None
    normalized = value.strip().lower()

    status_mapping = {
        "dnf": "DNF",
        "did not finish": "DNF",
        "dns": "DNS",
        "did not start": "DNS",
        "dsq": "DSQ",
        "dq": "DSQ",
        "disqualified": "DSQ",
        "lap": "LAP",
        "lapped": "LAP",
        "otl": "OTL",
        "outside time limit": "OTL",
        "np": "DNF",
        "not placed": "DNF",
        "nc": "DNF",
        "not classified": "DNF",
        "wd": "DNS",
        "withdrawn": "DNS",
    }

    for pattern, code in status_mapping.items():
        if pattern in normalized:
            return code

    return None


def parse_time_to_seconds(time_str: str | None) -> float | None:
    """
    Parse a time string into total seconds.

    Handles multiple formats commonly found in Skimo timing:
    - HH:MM:SS.ms (e.g., "1:23:45.6")
    - MM:SS.ms (e.g., "23:45.67")
    - SS.ms (e.g., "45.678")
    - Gap format with +/- prefix (e.g., "+1:23.4")

    Args:
        time_str: Time string to parse

    Returns:
        Time in seconds as float, or None if unparseable or status code

    Examples:
        >>> parse_time_to_seconds("1:23:45.6")
        5025.6
        >>> parse_time_to_seconds("23:45")
        1425.0
        >>> parse_time_to_seconds("+0:12.34")
        12.34
        >>> parse_time_to_seconds("DNF")
        None
    """
    if time_str is None:
        return None

    cleaned = time_str.strip()
    if not cleaned:
        return None

    if is_status_code(cleaned):
        return None

    cleaned = cleaned.lstrip("(").rstrip(")")
    cleaned = re.sub(r"['\"]", "", cleaned)

    match = TIME_PATTERN_HMS.match(cleaned)
    if match:
        return _extract_seconds_from_match(match)

    match = TIME_PATTERN_MS_ONLY.match(cleaned)
    if match:
        return _extract_seconds_from_match(match)

    match = TIME_PATTERN_SECONDS_ONLY.match(cleaned)
    if match:
        return _extract_seconds_from_match(match)

    return None


def _extract_seconds_from_match(match: re.Match[str]) -> float:
    """Extract total seconds from a regex match object."""
    groups = match.groupdict()

    sign = -1 if groups.get("sign") == "-" else 1
    hours = int(groups.get("hours") or 0)
    minutes = int(groups.get("minutes") or 0)
    seconds = int(groups.get("seconds") or 0)

    ms_str = groups.get("ms") or "0"
    ms_str = ms_str.ljust(3, "0")[:3]
    milliseconds = int(ms_str)

    total = hours * 3600 + minutes * 60 + seconds + milliseconds / 1000
    return sign * total


def parse_time_to_timedelta(time_str: str | None) -> timedelta | None:
    """
    Parse a time string into a timedelta object.

    Args:
        time_str: Time string to parse

    Returns:
        timedelta object, or None if unparseable

    Examples:
        >>> parse_time_to_timedelta("1:23:45")
        datetime.timedelta(seconds=5025)
        >>> parse_time_to_timedelta("DNF")
        None
    """
    seconds = parse_time_to_seconds(time_str)
    if seconds is None:
        return None
    return timedelta(seconds=seconds)


def seconds_to_time_string(seconds: float | None, include_hours: bool = True) -> str | None:
    """
    Convert seconds to a formatted time string.

    Args:
        seconds: Time in seconds
        include_hours: Whether to include hours even if zero

    Returns:
        Formatted time string or None

    Examples:
        >>> seconds_to_time_string(5025.6)
        '1:23:45.600'
        >>> seconds_to_time_string(125.5, include_hours=False)
        '2:05.500'
    """
    if seconds is None:
        return None

    sign = ""
    if seconds < 0:
        sign = "-"
        seconds = abs(seconds)

    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    ms = int((seconds - int(seconds)) * 1000)

    if include_hours or hours > 0:
        return f"{sign}{hours}:{minutes:02d}:{secs:02d}.{ms:03d}"
    return f"{sign}{minutes}:{secs:02d}.{ms:03d}"


def parse_gap_time(gap_str: str | None) -> float | None:
    """
    Parse a gap time string (time behind leader).

    Gap strings typically have a '+' prefix and may be in various formats.

    Args:
        gap_str: Gap time string (e.g., "+1:23.4", "+0:05")

    Returns:
        Gap in seconds, or None if unparseable

    Examples:
        >>> parse_gap_time("+1:23.4")
        83.4
        >>> parse_gap_time("0:00")  # Leader
        0.0
    """
    if gap_str is None:
        return None

    cleaned = gap_str.strip()
    if not cleaned:
        return None

    if cleaned == "-" or cleaned == "--":
        return 0.0

    return parse_time_to_seconds(cleaned)


def normalize_name(name: str | None) -> str | None:
    """
    Normalize athlete name formatting.

    Handles various name formats:
    - "LASTNAME Firstname" -> "Firstname Lastname"
    - "lastname, firstname" -> "Firstname Lastname"
    - Removes extra whitespace

    Args:
        name: Raw name string

    Returns:
        Normalized name or None

    Examples:
        >>> normalize_name("SMITH John")
        'John Smith'
        >>> normalize_name("Smith, John")
        'John Smith'
    """
    if not name:
        return None

    name = " ".join(name.split())

    if "," in name:
        parts = name.split(",", 1)
        if len(parts) == 2:
            last, first = parts
            name = f"{first.strip()} {last.strip()}"

    words = name.split()
    if len(words) >= 2:
        all_caps = [w for w in words if w.isupper() and len(w) > 1]
        mixed = [w for w in words if not w.isupper() or len(w) <= 1]

        if len(all_caps) >= 1 and len(mixed) >= 1:
            last_parts = [w.title() for w in all_caps]
            first_parts = mixed
            name = " ".join(first_parts + last_parts)
        else:
            name = " ".join(w.title() if w.isupper() else w for w in words)

    return name


def parse_rank(rank_str: str | None) -> int | None:
    """
    Parse a rank/position string.

    Args:
        rank_str: Rank string (e.g., "1", "1st", "12.")

    Returns:
        Integer rank or None

    Examples:
        >>> parse_rank("1")
        1
        >>> parse_rank("12.")
        12
        >>> parse_rank("DNF")
        None
    """
    if not rank_str:
        return None

    cleaned = rank_str.strip()
    if is_status_code(cleaned):
        return None

    cleaned = re.sub(r"(st|nd|rd|th|\.|\s)$", "", cleaned, flags=re.IGNORECASE)

    try:
        rank = int(cleaned)
        return rank if rank > 0 else None
    except ValueError:
        return None


def parse_bib_number(bib_str: str | None) -> str | None:
    """
    Parse and normalize a bib number.

    Args:
        bib_str: Bib number string

    Returns:
        Normalized bib string or None

    Examples:
        >>> parse_bib_number("42")
        '42'
        >>> parse_bib_number("#42")
        '42'
    """
    if not bib_str:
        return None

    cleaned = bib_str.strip()
    cleaned = cleaned.lstrip("#")
    cleaned = cleaned.strip()

    return cleaned if cleaned else None


def extract_nationality_from_name(name: str) -> tuple[str, str | None]:
    """
    Extract nationality code from a name string.

    Some sources include nationality in parentheses after the name.

    Args:
        name: Name string potentially containing nationality

    Returns:
        Tuple of (clean_name, nationality_code or None)

    Examples:
        >>> extract_nationality_from_name("John Smith (USA)")
        ('John Smith', 'USA')
        >>> extract_nationality_from_name("John Smith")
        ('John Smith', None)
    """
    if not name:
        return name, None

    match = re.search(r"\s*\(([A-Z]{2,3})\)\s*$", name)
    if match:
        nationality = match.group(1)
        clean_name = name[: match.start()].strip()
        return clean_name, nationality

    return name, None
