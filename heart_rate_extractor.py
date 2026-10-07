import os, sys, argparse, datetime, xml.etree.ElementTree as ET, glob, math

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

def parse_time(tstr):
    try:
        dt = datetime.datetime.fromisoformat(tstr.replace('Z','+00:00'))
    except Exception:
        dt = datetime.datetime.strptime(tstr, '%Y-%m-%dT%H:%M:%S')
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt

def haversine_distance_ft(lat1, lon1, lat2, lon2):
    R = 20902231.0  # Earth radius in feet (mean radius ~ 6,371,000 meters)
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def format_elapsed_time(seconds):
    total_sec = max(0, int(round(seconds)))
    hours = total_sec // 3600
    minutes = (total_sec % 3600) // 60
    sec = total_sec % 60
    return f"{hours}:{minutes:02d}:{sec:02d}"

def extract_tcx_data(file_path, start_time=None):
    ns = {'ns': 'http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2'}
    tree = ET.parse(file_path)
    root = tree.getroot()

    activity_time = None
    id_el = root.find('.//ns:Id', ns)
    if id_el is not None and id_el.text:
        try:
            activity_time = parse_time(id_el.text)
        except Exception:
            pass

    tps = root.findall('.//ns:Trackpoint', ns)
    hrs = []
    times = []
    positions = []
    for tp in tps:
        time_el = tp.find('ns:Time', ns)
        if time_el is None or not time_el.text:
            continue
        t = parse_time(time_el.text)
        hr_el = tp.find('.//ns:HeartRateBpm/ns:Value', ns)
        if hr_el is not None and hr_el.text:
            try:
                hrs.append(int(hr_el.text))
                times.append(t)
            except ValueError:
                pass
        pos_el = tp.find('ns:Position', ns)
        if pos_el is not None:
            lat_el = pos_el.find('ns:LatitudeDegrees', ns)
            lon_el = pos_el.find('ns:LongitudeDegrees', ns)
            if lat_el is not None and lon_el is not None and lat_el.text and lon_el.text:
                try:
                    positions.append((t, float(lat_el.text), float(lon_el.text)))
                except ValueError:
                    pass

    max_hr, avg_hr, max_time = None, None, None
    if hrs:
        filter_start = start_time if start_time is not None else times[0]
        filtered = [(t, h) for t, h in zip(times, hrs) if t >= filter_start]
        if filtered:
            max_hr = max(h for t, h in filtered)
            max_time = next(t for t, h in filtered if h == max_hr)
            avg_hr = sum(h for t, h in filtered) / len(filtered)

    sort_time = max_time or activity_time or (positions[0][0] if positions else None)

    location_matches = []
    if positions:
        act_start = start_time if start_time is not None else positions[0][0]

        # Waypoints 0..4 (Start through Lower Most) are outbound.
        # Waypoint 5 (Turn Around) is the midpoint turnaround.
        # Waypoints 6..10 (Trail End through End) are inbound.
        if len(positions) >= 20:
            turn_lat, turn_lon = REFERENCE_TABLE[5][2], REFERENCE_TABLE[5][3]
            mid_start = int(len(positions) * 0.25)
            mid_end = max(mid_start + 1, int(len(positions) * 0.75))
            sub_slice = positions[mid_start:mid_end]
            best_sub = min(range(len(sub_slice)), key=lambda i: haversine_distance_ft(turn_lat, turn_lon, sub_slice[i][1], sub_slice[i][2]))
            turn_idx = mid_start + best_sub

            out_points = positions[:turn_idx]
            back_points = positions[turn_idx:]

            curr_out_idx = 0
            curr_back_idx = 0
            for idx, (where, ref_when, rlat, rlon) in enumerate(REFERENCE_TABLE):
                if idx < 5:
                    sub = out_points[curr_out_idx:] if curr_out_idx < len(out_points) else out_points
                    best_i = min(range(len(sub)), key=lambda i: haversine_distance_ft(rlat, rlon, sub[i][1], sub[i][2]))
                    actual_i = curr_out_idx + best_i if curr_out_idx < len(out_points) else best_i
                    pt = out_points[actual_i]
                    curr_out_idx = actual_i
                elif idx == 5:
                    pt = positions[turn_idx]
                else:
                    sub = back_points[curr_back_idx:] if curr_back_idx < len(back_points) else back_points
                    best_i = min(range(len(sub)), key=lambda i: haversine_distance_ft(rlat, rlon, sub[i][1], sub[i][2]))
                    actual_i = curr_back_idx + best_i if curr_back_idx < len(back_points) else best_i
                    pt = back_points[actual_i]
                    curr_back_idx = actual_i

                dist_ft = haversine_distance_ft(rlat, rlon, pt[1], pt[2])
                elapsed_sec = (pt[0] - act_start).total_seconds()
                location_matches.append({
                    'where': where,
                    'when': format_elapsed_time(elapsed_sec),
                    'lat': pt[1],
                    'long': pt[2],
                    'diff_ft': dist_ft
                })
        else:
            for where, ref_when, ref_lat, ref_lon in REFERENCE_TABLE:
                best_pt = min(positions, key=lambda p: haversine_distance_ft(ref_lat, ref_lon, p[1], p[2]))
                dist_ft = haversine_distance_ft(ref_lat, ref_lon, best_pt[1], best_pt[2])
                elapsed_sec = (best_pt[0] - act_start).total_seconds()
                location_matches.append({
                    'where': where,
                    'when': format_elapsed_time(elapsed_sec),
                    'lat': best_pt[1],
                    'long': best_pt[2],
                    'diff_ft': dist_ft
                })

    return max_hr, avg_hr, max_time, sort_time, location_matches

def extract_hr_from_tcx(file_path, start_time=None):
    max_hr, avg_hr, max_time, _, _ = extract_tcx_data(file_path, start_time)
    return max_hr, avg_hr, max_time

def print_reference_table():
    print("Reference Table (Where 20261006):")
    print("Where\tWhen\tLat\tLong")
    for where, when, lat, lon in REFERENCE_TABLE:
        print(f"{where}\t{when}\t{lat:.6f}\t{lon:.6f}")
    print()

def print_location_table(location_results):
    print("Where\tWhen\tLat\tLong\tPosition Difference (ft)")
    for row in location_results:
        print(f"{row['where']}\t{row['when']}\t{row['lat']:.6f}\t{row['long']:.6f}\t{row['diff_ft']:.1f}")

def main():
    parser = argparse.ArgumentParser(description='Extract max and average heart rate, and waypoint times from TCX files')
    parser.add_argument('--data-dir', default='data', help='Directory containing .tcx files')
    parser.add_argument('--start-time', help='ISO 8601 start time; default is first timestamp in each file')
    args = parser.parse_args()
    start_time = parse_time(args.start_time) if args.start_time else None
    pattern = os.path.join(args.data_dir, '*')
    results = []
    for file_path in glob.glob(pattern):
        if not file_path.lower().endswith('.tcx'):
            continue
        max_hr, avg_hr, max_time, sort_time, locs = extract_tcx_data(file_path, start_time)
        results.append((file_path, max_hr, avg_hr, max_time, sort_time, locs))

    def get_sort_key(item):
        file_path, max_hr, avg_hr, max_time, sort_time, locs = item
        if isinstance(sort_time, datetime.datetime):
            if sort_time.tzinfo is None:
                return (sort_time.replace(tzinfo=datetime.timezone.utc), file_path)
            return (sort_time, file_path)
        return (datetime.datetime.min.replace(tzinfo=datetime.timezone.utc), file_path)

    results.sort(key=get_sort_key)

    print_reference_table()

    for file_path, max_hr, avg_hr, max_time, sort_time, locs in results:
        if max_hr is None:
            print(f'{os.path.basename(file_path)}: No heart rate data found')
        else:
            time_str = max_time.isoformat() if isinstance(max_time, datetime.datetime) else str(max_time)
            print(f'{os.path.basename(file_path)}: Max HR = {max_hr} (at {time_str}), Avg HR = {avg_hr:.1f}')
        if locs:
            print_location_table(locs)
        else:
            print('  No GPS position data found')
        print()

if __name__ == '__main__':
    main()


