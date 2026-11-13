#!/usr/bin/env python3
"""Update public holiday JSON from Korea Astronomy and Space Science Institute Open API.
Requires KASI_SERVICE_KEY (GitHub Actions repository secret). Never publish the key.
"""
import datetime as dt
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'holidays.json'
KEY = os.environ.get('KASI_SERVICE_KEY', '').strip()
if not KEY:
    raise SystemExit('Missing repository secret KASI_SERVICE_KEY')

# Existing data is preserved if a year has not been published or the API fails.
feed = json.loads(PATH.read_text(encoding='utf-8'))
years = dict(feed.get('years', {}))
today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
current_year = today.year
updated = 0
errors = []
for year in range(current_year - 1, current_year + 4):
    params = urllib.parse.urlencode({'ServiceKey': KEY, 'solYear': str(year), 'numOfRows': '200'})
    url = 'https://apis.data.go.kr/B090041/openapi/service/SpcdeInfoService/getRestDeInfo?' + params
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'ShiftCalendarHolidayUpdater/1.0'})
        with urllib.request.urlopen(req, timeout=35) as res:
            xml = res.read()
        root = ET.fromstring(xml)
        result_code = root.findtext('.//resultCode')
        if result_code and result_code not in ('00', '0'):
            raise ValueError(f'API resultCode {result_code}: {root.findtext(".//resultMsg")}')
        pairs = {}
        for item in root.findall('.//item'):
            if item.findtext('isHoliday', '').upper() != 'Y':
                continue
            raw = (item.findtext('locdate') or '').strip()
            name = (item.findtext('dateName') or '공휴일').strip()
            if len(raw) != 8 or not raw.isdigit() or int(raw[:4]) != year:
                continue
            day = dt.datetime.strptime(raw, '%Y%m%d').date().strftime('%m-%d')
            if day in pairs and name != pairs[day]:
                pairs[day] += '·' + name
            else:
                pairs[day] = name
        if len(pairs) < 5:
            # Unpublished future years should not erase preexisting values.
            print(f'{year}: insufficient data ({len(pairs)}), retained prior values')
            continue
        ordered = dict(sorted(pairs.items()))
        if years.get(str(year)) != ordered:
            years[str(year)] = ordered
            updated += 1
        print(f'{year}: {len(pairs)} holiday dates')
    except Exception as exc:
        errors.append(f'{year}: {exc}')

if not updated and feed.get('source') != 'KASI-OpenAPI' and not errors:
    print('No changes to data')
if errors:
    print('API warnings: ' + '; '.join(errors))
if not any(str(year) in years and len(years[str(year)]) >= 5 for year in (current_year, current_year+1)):
    raise SystemExit('No usable current/next year holiday data; refuse to update')
if errors and updated == 0:
    raise SystemExit('All API requests failed; old data left intact')
# Only write file when holiday values actually change (or first successful run).
if updated or feed.get('source') != 'KASI-OpenAPI':
    new = {'source': 'KASI-OpenAPI', 'updatedAt': today.isoformat(), 'years': years}
    PATH.write_text(json.dumps(new, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Updated holidays.json')
else:
    print('Already up to date')
