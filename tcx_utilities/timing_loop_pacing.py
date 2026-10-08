"""Match GPS trackpoints to loop waypoints for pacing charts."""

from __future__ import annotations

import argparse
from datetime import datetime
import math

from tcx_utilities.shared import (
    TcxActivity,
    add_common_arguments,
    datetime_sort_key,
    load_tcx,
    parse_start_time,
    resolve_tcx_files,
)

# Waypoints 0..4 (Start through Lower Most) are outbound.
# Waypoint 5 (Turn Around) is the midpoint turnaround.
# Waypoints 6..10 (Trail End through End) are inbound.
REFERENCE_TABLE = [
    ("Start", "0:00:00", 48.213993, -122.729362),
    ("Power Line", "0:02:53", 48.213978, -122.740448),
    ("Winterhawk Out", "0:05:39", 48.212208, -122.739708),
    ("Trail Start", "0:07:54", 48.209930, -122.738724),
    ("Lower Most", "0:17:00", 48.207470, -122.735039),
    ("Turn Around", "0:30:35", 48.210117, -122.730797),
    ("Trail End", "0:45:50", 48.209934, -122.738770),
    ("Winterhawk Back", "0:48:05", 48.212349, -122.739761),
    ("Power Line", "0:50:20", 48.213776, -122.740295),
    ("Trun Around", "0:52:30", 48.215134, -122.736534),
    ("End", "0:55:18", 48.213829, -122.729362),
]

TURNAROUND_INDEX = 5
MIN_POINTS_FOR_SPLIT = 20
EARTH_RADIUS_FT = 20_902_231.0  # mean Earth radius in feet


def haversine_distance_ft(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return EARTH_RADIUS_FT * c


def format_elapsed_time(seconds: float) -> str:
    total_sec = max(0, int(round(seconds)))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    sec = total_sec % 60
    return f"{hours}:{minutes:02d}:{sec:02d}"


def _match_row(
    where: str,
    ref_lat: float,
    ref_lon: float,
    point: tuple[datetime, float, float],
    act_start: datetime,
) -> dict:
    return {
        "where": where,
        "when": format_elapsed_time((point[0] - act_start).total_seconds()),
        "lat": point[1],
        "long": point[2],
        "diff_ft": haversine_distance_ft(ref_lat, ref_lon, point[1], point[2]),
    }


def match_waypoints(
    positions: list[tuple[datetime, float, float]],
    start_time: datetime | None = None,
) -> list[dict]:
    if not positions:
        return []

    act_start = start_time if start_time is not None else positions[0][0]
    location_matches: list[dict] = []

    if len(positions) >= MIN_POINTS_FOR_SPLIT:
        turn_lat, turn_lon = REFERENCE_TABLE[TURNAROUND_INDEX][2], REFERENCE_TABLE[TURNAROUND_INDEX][3]
        mid_start = int(len(positions) * 0.25)
        mid_end = max(mid_start + 1, int(len(positions) * 0.75))
        sub_slice = positions[mid_start:mid_end]
        best_sub = min(
            range(len(sub_slice)),
            key=lambda i: haversine_distance_ft(turn_lat, turn_lon, sub_slice[i][1], sub_slice[i][2]),
        )
        turn_idx = mid_start + best_sub
        out_points = positions[:turn_idx]
        back_points = positions[turn_idx:]

        curr_out_idx = 0
        curr_back_idx = 0
        for idx, (where, _ref_when, rlat, rlon) in enumerate(REFERENCE_TABLE):
            if idx < TURNAROUND_INDEX:
                sub = out_points[curr_out_idx:] if curr_out_idx < len(out_points) else out_points
                best_i = min(
                    range(len(sub)),
                    key=lambda i: haversine_distance_ft(rlat, rlon, sub[i][1], sub[i][2]),
                )
                actual_i = curr_out_idx + best_i if curr_out_idx < len(out_points) else best_i
                pt = out_points[actual_i]
                curr_out_idx = actual_i
            elif idx == TURNAROUND_INDEX:
                pt = positions[turn_idx]
            else:
                sub = back_points[curr_back_idx:] if curr_back_idx < len(back_points) else back_points
                best_i = min(
                    range(len(sub)),
                    key=lambda i: haversine_distance_ft(rlat, rlon, sub[i][1], sub[i][2]),
                )
                actual_i = curr_back_idx + best_i if curr_back_idx < len(back_points) else best_i
                pt = back_points[actual_i]
                curr_back_idx = actual_i
            location_matches.append(_match_row(where, rlat, rlon, pt, act_start))
        return location_matches

    for where, _ref_when, ref_lat, ref_lon in REFERENCE_TABLE:
        best_pt = min(
            positions,
            key=lambda p: haversine_distance_ft(ref_lat, ref_lon, p[1], p[2]),
        )
        location_matches.append(_match_row(where, ref_lat, ref_lon, best_pt, act_start))
    return location_matches


def print_reference_table() -> None:
    print("Reference Table (Where 20261006):")
    print("Where\tWhen\tLat\tLong")
    for where, when, lat, lon in REFERENCE_TABLE:
        print(f"{where}\t{when}\t{lat:.6f}\t{lon:.6f}")
    print()


def print_location_table(location_results: list[dict]) -> None:
    print("Where\tWhen\tLat\tLong\tPosition Difference (ft)")
    for row in location_results:
        print(
            f"{row['where']}\t{row['when']}\t{row['lat']:.6f}\t{row['long']:.6f}\t{row['diff_ft']:.1f}"
        )


def _activity_sort_time(activity: TcxActivity, start_time: datetime | None) -> datetime | None:
    positions = activity.positions
    if start_time is not None:
        return start_time
    if positions:
        return positions[0][0]
    return activity.activity_time


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Estimate loop waypoint times from TCX GPS tracks"
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

    activities = [load_tcx(path) for path in files]
    activities.sort(
        key=lambda activity: datetime_sort_key(
            _activity_sort_time(activity, start_time),
            activity.path.name,
        )
    )

    print_reference_table()
    for activity in activities:
        print(activity.path.name)
        locs = match_waypoints(activity.positions, start_time)
        if locs:
            print_location_table(locs)
        else:
            print("  No GPS position data found")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
