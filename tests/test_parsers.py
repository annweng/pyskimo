"""
Unit tests for HTML and PDF parsers using mocked responses.

These tests use fixture data to ensure parsing works correctly
without making actual network requests.
"""

import pytest

from pyskimo.parsers.html_parser import HTMLResultParser, parse_results_html
from pyskimo.schemas import RaceFormat, ResultStatus

SAMPLE_RESULTS_HTML = """
<!DOCTYPE html>
<html>
<head><title>Race Results</title></head>
<body>
<h1>World Cup Sprint - Andorra 2024</h1>
<table class="results-table">
    <thead>
        <tr>
            <th>Rank</th>
            <th>Bib</th>
            <th>Name</th>
            <th>Nationality</th>
            <th>Category</th>
            <th>Time</th>
            <th>Gap</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>1</td>
            <td>42</td>
            <td>JORNET Kilian</td>
            <td>ESP</td>
            <td>Senior Men</td>
            <td>4:32.56</td>
            <td>-</td>
        </tr>
        <tr>
            <td>2</td>
            <td>15</td>
            <td>BOSCACCI Michele</td>
            <td>ITA</td>
            <td>Senior Men</td>
            <td>4:45.12</td>
            <td>+0:12.56</td>
        </tr>
        <tr>
            <td>3</td>
            <td>23</td>
            <td>BON MARDION William</td>
            <td>FRA</td>
            <td>Senior Men</td>
            <td>4:48.90</td>
            <td>+0:16.34</td>
        </tr>
        <tr>
            <td>-</td>
            <td>7</td>
            <td>PALZER Anton</td>
            <td>GER</td>
            <td>Senior Men</td>
            <td>DNF</td>
            <td></td>
        </tr>
        <tr>
            <td>-</td>
            <td>31</td>
            <td>MAGNINI Davide</td>
            <td>ITA</td>
            <td>Senior Men</td>
            <td>DSQ</td>
            <td></td>
        </tr>
    </tbody>
</table>
</body>
</html>
"""

SAMPLE_RESULTS_WITH_SPLITS_HTML = """
<!DOCTYPE html>
<html>
<body>
<table class="results">
    <thead>
        <tr>
            <th>Pos</th>
            <th>Name</th>
            <th>NAT</th>
            <th>Split 1</th>
            <th>Split 2</th>
            <th>Finish</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>1</td>
            <td>John Smith (USA)</td>
            <td>USA</td>
            <td>10:23.4</td>
            <td>25:45.6</td>
            <td>45:32.1</td>
        </tr>
        <tr>
            <td>2</td>
            <td>Maria Garcia</td>
            <td>ESP</td>
            <td>10:45.0</td>
            <td>26:12.3</td>
            <td>46:15.8</td>
        </tr>
    </tbody>
</table>
</body>
</html>
"""

SAMPLE_COMMA_NAME_HTML = """
<!DOCTYPE html>
<html>
<body>
<table class="ranking">
    <tr><th>Rank</th><th>Athlete</th><th>Time</th></tr>
    <tr><td>1</td><td>Smith, John</td><td>1:23:45</td></tr>
    <tr><td>2</td><td>Garcia, Maria</td><td>1:25:30</td></tr>
</table>
</body>
</html>
"""

SAMPLE_DIV_LAYOUT_HTML = """
<!DOCTYPE html>
<html>
<body>
<div class="result-item">
    <span class="rank">1</span>
    <span class="athlete-name">John Smith (USA)</span>
    <span class="result-time">1:23:45.5</span>
</div>
<div class="result-item">
    <span class="rank">2</span>
    <span class="athlete-name">Maria Garcia (ESP)</span>
    <span class="result-time">1:25:30.2</span>
</div>
<div class="result-item">
    <span class="rank">-</span>
    <span class="athlete-name">Pierre Dupont (FRA)</span>
    <span class="result-time">DNF</span>
</div>
</body>
</html>
"""


class TestHTMLResultParser:
    """Tests for the HTML result parser."""

    def test_parse_basic_results_table(self) -> None:
        """Test parsing a standard results table."""
        results = parse_results_html(SAMPLE_RESULTS_HTML)

        assert len(results) == 5

        first = results[0]
        assert first.rank == 1
        assert first.bib == "42"
        assert "Kilian" in first.athlete.full_name or "JORNET" in first.athlete.full_name
        assert first.athlete.nationality == "ESP"
        assert first.athlete.category == "Senior Men"
        assert first.status == ResultStatus.FINISHED
        assert first.time_seconds is not None
        assert first.time_seconds == pytest.approx(272.56, rel=0.01)

    def test_parse_gap_times(self) -> None:
        """Test that gap times are parsed correctly."""
        results = parse_results_html(SAMPLE_RESULTS_HTML)

        second = results[1]
        assert second.gap_seconds is not None
        assert second.gap_seconds == pytest.approx(12.56, rel=0.01)

        first = results[0]
        assert first.gap_seconds == 0.0 or first.gap_seconds is None

    def test_parse_dnf_status(self) -> None:
        """Test that DNF status is correctly identified."""
        results = parse_results_html(SAMPLE_RESULTS_HTML)

        dnf_result = next(r for r in results if r.status == ResultStatus.DNF)
        assert dnf_result.athlete.full_name is not None
        assert "PALZER" in dnf_result.athlete.full_name or "Anton" in dnf_result.athlete.full_name
        assert dnf_result.rank is None
        assert dnf_result.time_seconds is None

    def test_parse_dsq_status(self) -> None:
        """Test that DSQ status is correctly identified."""
        results = parse_results_html(SAMPLE_RESULTS_HTML)

        dsq_result = next(r for r in results if r.status == ResultStatus.DSQ)
        assert dsq_result.athlete.nationality == "ITA"
        assert dsq_result.time_seconds is None

    def test_parse_with_event_metadata(self) -> None:
        """Test that event/race IDs are attached to results."""
        results = parse_results_html(
            SAMPLE_RESULTS_HTML,
            event_id="wc-andorra-2024",
            race_id="sprint-men",
            race_format=RaceFormat.SPRINT,
        )

        for result in results:
            assert result.event_id == "wc-andorra-2024"
            assert result.race_id == "sprint-men"
            assert result.race_format == RaceFormat.SPRINT

    def test_parse_with_splits(self) -> None:
        """Test parsing results with intermediate splits."""
        results = parse_results_html(SAMPLE_RESULTS_WITH_SPLITS_HTML)

        assert len(results) == 2
        first = results[0]

        assert len(first.splits) >= 1

    def test_parse_comma_separated_names(self) -> None:
        """Test parsing names in 'Last, First' format."""
        results = parse_results_html(SAMPLE_COMMA_NAME_HTML)

        assert len(results) == 2
        assert any(
            "John" in r.athlete.full_name and "Smith" in r.athlete.full_name for r in results
        )

    def test_parse_nationality_from_name(self) -> None:
        """Test extracting nationality from name field."""
        results = parse_results_html(SAMPLE_RESULTS_WITH_SPLITS_HTML)

        first = results[0]
        assert first.athlete.nationality == "USA"

    def test_empty_html(self) -> None:
        """Test handling of empty or minimal HTML."""
        results = parse_results_html("<html><body></body></html>")
        assert results == []

    def test_no_results_table(self) -> None:
        """Test handling of HTML without results table."""
        html = "<html><body><p>No results available</p></body></html>"
        results = parse_results_html(html)
        assert results == []


class TestHTMLResultParserClass:
    """Tests for HTMLResultParser class methods."""

    def test_parser_initialization(self) -> None:
        """Test parser initializes with correct metadata."""
        parser = HTMLResultParser(
            event_id="test-event",
            race_id="test-race",
            race_format=RaceFormat.VERTICAL,
        )
        assert parser.event_id == "test-event"
        assert parser.race_id == "test-race"
        assert parser.race_format == RaceFormat.VERTICAL

    def test_column_mapping(self) -> None:
        """Test that column mapping works for various header names."""
        parser = HTMLResultParser()

        headers1 = ["rank", "bib", "name", "time"]
        map1 = parser._map_columns(headers1)
        assert "rank" in map1
        assert "bib" in map1
        assert "name" in map1
        assert "time" in map1

        headers2 = ["pos", "no", "athlete", "result"]
        map2 = parser._map_columns(headers2)
        assert "rank" in map2
        assert "bib" in map2
        assert "name" in map2
        assert "time" in map2

    def test_result_validation(self) -> None:
        """Test that results are validated through Pydantic."""
        results = parse_results_html(SAMPLE_RESULTS_HTML)

        for result in results:
            assert result.athlete.full_name
            assert result.athlete.full_name.strip() != ""


class TestDivLayoutParser:
    """Tests for div-based layout parsing."""

    def test_parse_div_layout(self) -> None:
        """Test parsing div-based result layouts."""
        results = parse_results_html(SAMPLE_DIV_LAYOUT_HTML)

        assert len(results) >= 2

        finished = [r for r in results if r.status == ResultStatus.FINISHED]
        assert len(finished) >= 2

    def test_div_dnf_handling(self) -> None:
        """Test DNF handling in div layouts."""
        results = parse_results_html(SAMPLE_DIV_LAYOUT_HTML)

        dnf_results = [r for r in results if r.status == ResultStatus.DNF]
        assert len(dnf_results) >= 1


class TestResultDataIntegrity:
    """Tests for data integrity and consistency."""

    def test_time_seconds_matches_raw(self) -> None:
        """Test that parsed seconds match raw time strings."""
        results = parse_results_html(SAMPLE_RESULTS_HTML)

        for result in results:
            if result.status == ResultStatus.FINISHED and result.time_raw:
                assert result.time_seconds is not None

    def test_ranks_are_sequential(self) -> None:
        """Test that ranks are properly ordered."""
        results = parse_results_html(SAMPLE_RESULTS_HTML)

        finished = [r for r in results if r.status == ResultStatus.FINISHED]
        ranks = [r.rank for r in finished if r.rank is not None]

        assert ranks == sorted(ranks)

    def test_flat_dict_conversion(self) -> None:
        """Test that results convert to flat dictionaries properly."""
        results = parse_results_html(SAMPLE_RESULTS_HTML)

        for result in results:
            flat = result.to_flat_dict()

            assert "athlete_full_name" in flat
            assert "rank" in flat
            assert "status" in flat
            assert "time_seconds" in flat

            assert flat["status"] in ["finished", "dnf", "dns", "dsq", "lap", "otl", "pending"]


class TestRealWorldFormats:
    """Tests for real ISMF and DataSkimo HTML formats."""

    ISMF_STYLE_HTML = """
    <table>
    <thead>
    <tr><th>Rank</th><th>Nation</th><th>Athlete</th><th>Total time</th><th>Gap</th><th>Year</th><th>ISMF ID</th><th>WC Pts</th></tr>
    </thead>
    <tbody>
    <tr bgcolor=#FFFFFF><td>1</td><td>(ESP)</td><td>CARDONA COLL Oriol</td><td>02:51.7</td><td>0</td><td>1994</td><td>613</td><td>100</td></tr>
    <tr bgcolor=#DDDDDD><td>2</td><td>(SUI)</td><td>LIETHA Arno</td><td>02:56.7</td><td>+0:05.0</td><td>1998</td><td>1499</td><td>90</td></tr>
    <tr bgcolor=#FFFFFF><td>3</td><td>(FRA)</td><td>ANSELMET Thibault</td><td>03:00.0</td><td>+0:08.3</td><td>1997</td><td>1541</td><td>81</td></tr>
    </tbody>
    </table>
    """

    DATASKIMO_STYLE_HTML = """
    <table>
    <thead>
    <tr><th>Rank</th><th width="48" align="center">Nation</th><th>Athete</th><th>Total time</th><th>Year</th><th>ISMF ID</th><th>WC Pts</th></tr>
    </thead>
    <tbody>
    <tr bgcolor=#FFFFFF><td>1</td><td width='48' align='center'><img src='flag/FRA.png' alt='FRA'></td><td><a href='athlete.php?id=2031'>HARROP&nbsp;Emily</a></td><td>03:12.5</td><td>1997</td><td>2031</td><td>100</td></tr>
    <tr bgcolor=#DDDDDD><td>2</td><td width='48' align='center'><img src='flag/ITA.png' alt='ITA'></td><td><a href='athlete.php?id=1365'>MURADA&nbsp;Giulia</a></td><td>03:18.2</td><td>1998</td><td>1365</td><td>90</td></tr>
    <tr bgcolor=#FFFFFF><td>-</td><td width='48' align='center'><img src='flag/ESP.png' alt='ESP'></td><td>GARCIA Ana</td><td>DNF</td><td>1999</td><td>1234</td><td>0</td></tr>
    </tbody>
    </table>
    """

    def test_ismf_format_basic_parsing(self) -> None:
        """Test parsing ISMF-style results with parenthesized nationality."""
        results = parse_results_html(self.ISMF_STYLE_HTML)

        assert len(results) == 3

        first = results[0]
        assert first.rank == 1
        assert first.athlete.nationality == "ESP"
        assert "CARDONA" in first.athlete.full_name or "Oriol" in first.athlete.full_name
        assert first.time_seconds is not None
        assert first.time_seconds == pytest.approx(171.7, rel=0.01)

    def test_ismf_format_birth_year(self) -> None:
        """Test that birth year is extracted from ISMF format."""
        results = parse_results_html(self.ISMF_STYLE_HTML)

        first = results[0]
        assert first.athlete.birth_year == 1994

        second = results[1]
        assert second.athlete.birth_year == 1998

    def test_ismf_format_athlete_id(self) -> None:
        """Test that ISMF ID is extracted."""
        results = parse_results_html(self.ISMF_STYLE_HTML)

        first = results[0]
        assert first.athlete.athlete_id == "613"

    def test_ismf_format_gap_parsing(self) -> None:
        """Test gap time parsing in ISMF format."""
        results = parse_results_html(self.ISMF_STYLE_HTML)

        second = results[1]
        assert second.gap_seconds is not None
        assert second.gap_seconds == pytest.approx(5.0, rel=0.01)

    def test_dataskimo_format_flag_nationality(self) -> None:
        """Test extracting nationality from flag image in DataSkimo format."""
        results = parse_results_html(self.DATASKIMO_STYLE_HTML)

        assert len(results) == 3

        first = results[0]
        assert first.athlete.nationality == "FRA"

        second = results[1]
        assert second.athlete.nationality == "ITA"

    def test_dataskimo_format_athlete_link(self) -> None:
        """Test parsing athlete names from links."""
        results = parse_results_html(self.DATASKIMO_STYLE_HTML)

        first = results[0]
        assert "HARROP" in first.athlete.full_name or "Emily" in first.athlete.full_name

    def test_dataskimo_format_dnf_handling(self) -> None:
        """Test DNF handling in DataSkimo format."""
        results = parse_results_html(self.DATASKIMO_STYLE_HTML)

        dnf_results = [r for r in results if r.status == ResultStatus.DNF]
        assert len(dnf_results) == 1
        assert dnf_results[0].athlete.nationality == "ESP"
        assert dnf_results[0].time_seconds is None

    def test_dataskimo_typo_athete_column(self) -> None:
        """Test that the 'Athete' typo in DataSkimo headers is handled."""
        results = parse_results_html(self.DATASKIMO_STYLE_HTML)
        assert len(results) == 3
        assert all(r.athlete.full_name for r in results)

    def test_points_extraction(self) -> None:
        """Test WC points extraction."""
        results = parse_results_html(self.ISMF_STYLE_HTML)

        first = results[0]
        assert first.points == 100.0

        second = results[1]
        assert second.points == 90.0
