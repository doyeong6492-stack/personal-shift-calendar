#!/usr/bin/env python3
"""Fetch Korean holidays AND non-holiday anniversaries for the personal calendar.
Requires repository secret KASI_SERVICE_KEY. The secret is never written to files.
"""
import datetime as dt
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
KEY = os.environ.get('KASI_SERVICE_KEY', '').strip()
if not KEY:
    raise SystemExit('Missing repository secret KASI_SERVICE_KEY')

TODAY = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
YEARS = range(TODAY.year - 1, TODAY.year + 4)
DATASETS = [
    ('holidays.json', 'getRestDeInfo', 5, True),
    ('anniversaries.json', 'getAnniversaryInfo', 3, False),
]

def fetch_year(year, endpoint, only_holidays):
    params = urllib.parse.urlencode({'ServiceKey': KEY, 'solYear': str(year), 'numOfRows': '250'})
    url = 'https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/' + endpoint + '?' + params
    request = urllib.request.Request(url, headers={'User-Agent': 'ShiftCalendarSpecialDaysUpdater/1.1'})
    with urllib.request.urlopen(request, timeout=35) as res:
        root = ET.fromstring(res.read())
    code = root.findtext('.//resultCode')
    if code and code not in ('00', '0'):
        raise ValueError('API resultCode ' + code + ': ' + str(root.findtext('.//resultMsg')))
    pairs = {}
    for item in root.findall('.//item'):
        is_holiday = (item.findtext('isHoliday') or '').upper()
        if only_holidays and is_holiday != 'Y':
            continue
        if not only_holidays and is_holiday == 'Y':
            continue  # 기념일을 공휴일/수당으로 혼동하지 않게 분리
        raw = (item.findtext('locdate') or '').strip()
        name = (item.findtext('dateName') or '').strip()
        if len(raw) != 8 or not raw.isdigit() or not name or int(raw[:4]) != year:
            continue
        try:
            day = dt.datetime.strptime(raw, '%Y%m%d').date().strftime('%m-%d')
        except ValueError:
            continue
        if day in pairs and name not in pairs[day].split('·'):
            pairs[day] += '·' + name
        else:
            pairs.setdefault(day, name)
    return dict(sorted(pairs.items()))

changed_any = False
successful_calls = 0
warnings = []
for filename, endpoint, min_count, only_holidays in DATASETS:
    path = ROOT / filename
    feed = json.loads(path.read_text(encoding='utf-8'))
    years = dict(feed.get('years', {}))
    changed = False
    dataset_successes = 0
    for year in YEARS:
        try:
            dates = fetch_year(year, endpoint, only_holidays)
            if len(dates) < min_count:
                print(f'{filename} {year}: insufficient entries ({len(dates)}); existing values retained')
                continue
            successful_calls += 1
            dataset_successes += 1
            if years.get(str(year)) != dates:
                years[str(year)] = dates
                changed = True
            print(f'{filename} {year}: {len(dates)} entries')
        except Exception as exc:
            warnings.append(f'{filename} {year}: {exc}')
    if changed or (dataset_successes and feed.get('source') != 'KASI-OpenAPI'):
        new = {'source': 'KASI-OpenAPI', 'updatedAt': TODAY.isoformat(), 'years': years}
        path.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        changed_any = True
        print(f'Updated {filename}')
    else:
        print(f'{filename}: no changes')
if warnings:
    print('API warnings: ' + '; '.join(warnings))
if successful_calls == 0:
    raise SystemExit('All special-date API requests failed; previous data preserved')
print('Done; file changes:', changed_any)
