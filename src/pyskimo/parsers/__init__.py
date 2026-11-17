"""
Parsers for extracting Skimo race data from various formats.

This module provides parsers for:
- HTML result tables from ISMF and DataSkimo portals
- Official PDF result sheets
"""

from pyskimo.parsers.html_parser import (
    HTMLResultParser,
    parse_calendar_html,
    parse_event_html,
    parse_results_html,
)
from pyskimo.parsers.pdf_parser import (
    PDFResultParser,
    parse_results_pdf,
)

__all__ = [
    "HTMLResultParser",
    "PDFResultParser",
    "parse_calendar_html",
    "parse_event_html",
    "parse_results_html",
    "parse_results_pdf",
]
