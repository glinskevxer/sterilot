from __future__ import annotations

from datetime import datetime

import pytest

from sterilot.errors import ValidationError
from sterilot.ingest.trace_import import load_trace

OFFSETS = """offset,temperature
0,100.0
60,133.0
300,133.4
360,120.0
"""

CLOCKS = """timestamp,temp_c
2025-06-16 08:00:00,100.0
2025-06-16 08:01:00,133.0
2025-06-16 08:06:00,133.4
"""


def test_a_trace_of_offsets_reads() -> None:
    result = load_trace(OFFSETS, datetime(2025, 6, 16, 8, 0))
    assert result.clean
    assert result.trace is not None
    assert len(result.trace) == 4
    assert result.trace.duration.seconds == pytest.approx(360.0)
    assert "4 samples over 6m" in result.summary()


def test_the_peak_comes_out_of_the_trace() -> None:
    result = load_trace(OFFSETS, datetime(2025, 6, 16, 8, 0))
    assert result.trace is not None
    assert result.trace.peak().celsius == pytest.approx(133.4)


def test_a_trace_of_clock_times_is_rebased_on_the_first_row() -> None:
    result = load_trace(CLOCKS)
    assert result.clean
    assert result.trace is not None
    assert result.trace.started_at == datetime(2025, 6, 16, 8, 0)
    assert result.trace.duration.seconds == pytest.approx(360.0)


def test_foreign_headers_are_aliased() -> None:
    text = OFFSETS.replace("offset,temperature", "Elapsed s,Chamber C")
    assert load_trace(text, datetime(2025, 6, 16, 8, 0)).clean


def test_a_temperature_that_will_not_read_is_reported() -> None:
    text = OFFSETS.replace("60,133.0", "60,hot")
    result = load_trace(text, datetime(2025, 6, 16, 8, 0))
    assert result.trace is not None
    assert len(result.trace) == 3
    assert "no readable temperature" in result.problems[0].describe()


def test_an_offset_that_will_not_read_is_reported() -> None:
    text = "offset,temperature\n0,100.0\nlater,133.0\n300,133.4\n"
    result = load_trace(text, datetime(2025, 6, 16, 8, 0))
    assert result.trace is not None
    assert len(result.trace) == 2


def test_a_file_with_one_usable_row_gives_no_trace() -> None:
    result = load_trace("offset,temperature\n0,100.0\n", datetime(2025, 6, 16, 8, 0))
    assert result.trace is None
    assert not result.clean
    assert "no trace read" in result.summary()


def test_a_file_mixing_clocks_and_offsets_is_refused() -> None:
    text = "offset,temperature\n2025-06-16 08:00:00,100.0\n60,133.0\n"
    with pytest.raises(ValidationError):
        load_trace(text)


def test_a_file_missing_a_column_is_refused() -> None:
    with pytest.raises(ValidationError):
        load_trace("offset\n0\n")


def test_a_short_row_is_rejected_and_the_rest_read() -> None:
    result = load_trace(OFFSETS + "400\n", datetime(2025, 6, 16, 8, 0))
    assert result.trace is not None
    assert len(result.trace) == 4
    assert not result.clean
