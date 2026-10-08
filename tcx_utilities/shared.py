"""Shared TCX parsing and CLI helpers."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

TCX_NS = {"ns": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2"}
DEFAULT_DATA_DIR = Path("data")


@dataclass(frozen=True)
class Trackpoint:
    time: datetime
    heart_rate: int | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class TcxActivity:
    path: Path
    activity_time: datetime | None
    trackpoints: tuple[Trackpoint, ...]

    @property
    def heart_rate_samples(self) -> list[tuple[datetime, int]]:
        return [
            (tp.time, tp.heart_rate)
            for tp in self.trackpoints
            if tp.heart_rate is not None
        ]

    @property
    def positions(self) -> list[tuple[datetime, float, float]]:
        return [
            (tp.time, tp.latitude, tp.longitude)
            for tp in self.trackpoints
            if tp.latitude is not None and tp.longitude is not None
        ]


def parse_time(tstr: str) -> datetime:
    """Parse a TCX or ISO-8601 timestamp into an aware UTC datetime."""
    try:
        dt = datetime.fromisoformat(tstr.replace("Z", "+00:00"))
    except ValueError:
        dt = datetime.strptime(tstr, "%Y-%m-%dT%H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_tcx(file_path: str | Path) -> TcxActivity:
    path = Path(file_path)
    tree = ET.parse(path)
    root = tree.getroot()

    activity_time = None
    id_el = root.find(".//ns:Id", TCX_NS)
    if id_el is not None and id_el.text:
        try:
            activity_time = parse_time(id_el.text)
        except ValueError:
            pass

    trackpoints: list[Trackpoint] = []
    for tp in root.findall(".//ns:Trackpoint", TCX_NS):
        time_el = tp.find("ns:Time", TCX_NS)
        if time_el is None or not time_el.text:
            continue
        t = parse_time(time_el.text)

        heart_rate = None
        hr_el = tp.find(".//ns:HeartRateBpm/ns:Value", TCX_NS)
        if hr_el is not None and hr_el.text:
            try:
                heart_rate = int(hr_el.text)
            except ValueError:
                pass

        latitude = longitude = None
        pos_el = tp.find("ns:Position", TCX_NS)
        if pos_el is not None:
            lat_el = pos_el.find("ns:LatitudeDegrees", TCX_NS)
            lon_el = pos_el.find("ns:LongitudeDegrees", TCX_NS)
            if lat_el is not None and lon_el is not None and lat_el.text and lon_el.text:
                try:
                    latitude = float(lat_el.text)
                    longitude = float(lon_el.text)
                except ValueError:
                    latitude = longitude = None

        trackpoints.append(
            Trackpoint(time=t, heart_rate=heart_rate, latitude=latitude, longitude=longitude)
        )

    return TcxActivity(path=path, activity_time=activity_time, trackpoints=tuple(trackpoints))


def add_common_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--data-file",
        nargs="+",
        metavar="PATH",
        help="TCX file(s) to process. Default: all .tcx files in --data-dir.",
    )
    parser.add_argument(
        "--data-dir",
        default=str(DEFAULT_DATA_DIR),
        help="Directory used when --data-file is omitted (default: data).",
    )
    parser.add_argument(
        "--start-time",
        help="ISO 8601 start time; default is the first timestamp in each file.",
    )
    return parser


def resolve_tcx_files(data_files: list[str] | None, data_dir: str | Path) -> list[Path]:
    """Return TCX paths from --data-file, or every .tcx file in data_dir."""
    if data_files:
        paths = [Path(raw) for raw in data_files]
        missing = [path for path in paths if not path.is_file()]
        if missing:
            names = ", ".join(str(path) for path in missing)
            raise FileNotFoundError(f"TCX file(s) not found: {names}")
        return paths

    directory = Path(data_dir)
    if not directory.is_dir():
        raise FileNotFoundError(f"Data directory not found: {directory}")

    files = sorted(
        {path.resolve(): path for path in directory.glob("*.tcx")}.values(),
        key=lambda path: path.name.lower(),
    )
    if not files:
        raise FileNotFoundError(f"No .tcx files found in {directory}")
    return files


def parse_start_time(value: str | None) -> datetime | None:
    return parse_time(value) if value else None


def datetime_sort_key(value: datetime | None, tiebreaker: str) -> tuple[datetime, str]:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return (value.replace(tzinfo=timezone.utc), tiebreaker)
        return (value, tiebreaker)
    return (datetime.min.replace(tzinfo=timezone.utc), tiebreaker)
