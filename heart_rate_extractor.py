import os, sys, argparse, datetime, xml.etree.ElementTree as ET, glob

def parse_time(tstr):
    try:
        dt = datetime.datetime.fromisoformat(tstr.replace('Z','+00:00'))
    except Exception:
        dt = datetime.datetime.strptime(tstr, '%Y-%m-%dT%H:%M:%S')
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt

def extract_hr_from_tcx(file_path, start_time=None):
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
    for tp in tps:
        time_el = tp.find('ns:Time', ns)
        hr_el = tp.find('.//ns:HeartRateBpm/ns:Value', ns)
        if time_el is None or hr_el is None:
            continue
        t = parse_time(time_el.text)
        times.append(t)
        hrs.append(int(hr_el.text))
    if not hrs:
        return None, None, activity_time
    if start_time is None:
        start_time = times[0]
    # Filter entries after start_time
    filtered = [(t, h) for t, h in zip(times, hrs) if t >= start_time]
    if not filtered:
        return None, None, activity_time
    max_hr = max(h for t, h in filtered)
    # Find timestamp of first occurrence of max HR
    max_time = next(t for t, h in filtered if h == max_hr)
    avg_hr = sum(h for t, h in filtered) / len(filtered)
    return max_hr, avg_hr, max_time

def main():
    parser = argparse.ArgumentParser(description='Extract max and average heart rate from TCX files')
    parser.add_argument('--data-dir', default='data', help='Directory containing .tcx files')
    parser.add_argument('--start-time', help='ISO 8601 start time; default is first timestamp in each file')
    args = parser.parse_args()
    start_time = parse_time(args.start_time) if args.start_time else None
    pattern = os.path.join(args.data_dir, '*')
    results = []
    for file_path in glob.glob(pattern):
        if not file_path.lower().endswith('.tcx'):
            continue
        max_hr, avg_hr, max_time = extract_hr_from_tcx(file_path, start_time)
        results.append((file_path, max_hr, avg_hr, max_time))

    def get_sort_key(item):
        file_path, max_hr, avg_hr, max_time = item
        if isinstance(max_time, datetime.datetime):
            if max_time.tzinfo is None:
                return (max_time.replace(tzinfo=datetime.timezone.utc), file_path)
            return (max_time, file_path)
        return (datetime.datetime.min.replace(tzinfo=datetime.timezone.utc), file_path)

    results.sort(key=get_sort_key)

    for file_path, max_hr, avg_hr, max_time in results:
        if max_hr is None:
            print(f'{os.path.basename(file_path)}: No heart rate data found')
        else:
            time_str = max_time.isoformat() if isinstance(max_time, datetime.datetime) else str(max_time)
            print(f'{os.path.basename(file_path)}: Max HR = {max_hr} (at {time_str}), Avg HR = {avg_hr:.1f}')

if __name__ == '__main__':
    main()

