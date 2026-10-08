"""Extract maximum and average heart rate from TCX files."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tcx_utilities.shared import (
    TcxActivity,
    add_common_arguments,
    datetime_sort_key,
    load_tcx,
    parse_start_time,
    resolve_tcx_files,
)


@dataclass(frozen=True)
class HeartRateSummary:
    path: Path
    max_hr: int | None
    avg_hr: float | None
    max_time: datetime | None
    sort_time: datetime | None


def summarize_heart_rate(activity: TcxActivity, start_time: datetime | None = None) -> HeartRateSummary:
    samples = activity.heart_rate_samples
    max_hr = avg_hr = max_time = None

    if samples:
        filter_start = start_time if start_time is not None else samples[0][0]
        filtered = [(t, hr) for t, hr in samples if t >= filter_start]
        if filtered:
            max_hr = max(hr for _, hr in filtered)
            max_time = next(t for t, hr in filtered if hr == max_hr)
            avg_hr = sum(hr for _, hr in filtered) / len(filtered)

    positions = activity.positions
    sort_time = max_time or activity.activity_time or (positions[0][0] if positions else None)
    return HeartRateSummary(
        path=activity.path,
        max_hr=max_hr,
        avg_hr=avg_hr,
        max_time=max_time,
        sort_time=sort_time,
    )


def format_heart_rate_line(summary: HeartRateSummary) -> str:
    name = summary.path.name
    if summary.max_hr is None or summary.avg_hr is None:
        return f"{name}: No heart rate data found"
    time_str = (
        summary.max_time.isoformat()
        if isinstance(summary.max_time, datetime)
        else str(summary.max_time)
    )
    return f"{name}: Max HR = {summary.max_hr} (at {time_str}), Avg HR = {summary.avg_hr:.1f}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract max and average heart rate from TCX files"
    )
    return add_common_arguments(parser)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    start_time = parse_start_time(args.start_time)
    try:
        files = resolve_tcx_files(args.data_file, args.data_dir)
    except FileNotFoundError as exc:
        print(exc)
        return 1

    summaries = [summarize_heart_rate(load_tcx(path), start_time) for path in files]
    summaries.sort(key=lambda item: datetime_sort_key(item.sort_time, item.path.name))

    for summary in summaries:
        print(format_heart_rate_line(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
