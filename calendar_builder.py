"""Generate reviewable T-Notes entries from Thiel's public calendar."""
import argparse
import datetime as dt
import html
import json
import os
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo
import requests
from bs4 import BeautifulSoup

BASE = 'https://www.thiel.edu'
SPORTS = {'WTEN': "women’s tennis", 'MTEN': "men’s tennis", 'WSOC': "women’s soccer", 'MSOC': "men’s soccer", 'WVB': "women’s volleyball", 'FOOT': 'football', 'WBB': "women’s basketball", 'MBB': "men’s basketball", 'BASE': 'baseball', 'SOFT': 'softball'}
MONTHS = ['', 'Jan.', 'Feb.', 'March', 'April', 'May', 'June', 'July', 'Aug.', 'Sept.', 'Oct.', 'Nov.', 'Dec.']

def clean(s):
    s = re.sub(r'\s+', ' ', html.unescape(s)).strip()
    for old, new in [('Washington and Jefferson', 'Washington & Jefferson'), ('St. Vincent', 'Saint Vincent'), ('Bi-weekly', 'Biweekly')]:
        s = s.replace(old, new)
    s = re.sub(r'\bbi-weekly\b', 'Biweekly', s, flags=re.I)
    return re.sub(r'\bPA\b', 'Pa.', s)

def ap_time(s):
    if re.search(r'\bnoon\b', s, re.I):
        return 'noon', 720
    if re.search(r'\bmidnight\b', s, re.I):
        return 'midnight', 0
    m = re.search(r'(\d{1,2})(?::(\d{2}))?\s*([ap])\.?m', s, re.I)
    if not m:
        return None, 1440
    h, minute, meridiem = int(m[1]), int(m[2] or 0), m[3].lower()
    if not 1 <= h <= 12 or minute > 59:
        return None, 1440
    order = (h % 12 + (12 if meridiem == 'p' else 0)) * 60 + minute
    if h == 12 and minute == 0:
        return ('noon' if meridiem == 'p' else 'midnight'), order
    return f'{h}' + (f':{minute:02}' if minute else '') + f' {meridiem}.m.', order

def location(s, sport):
    if sport in ["women’s soccer", "men’s soccer", 'football']:
        return 'Stoeber Field at Alumni Stadium'
    s = clean(s).replace('HMSC', 'Howard Miller Student Center')
    s = re.sub(r'\s+[-–/]\s+', ', ', s)
    if s.startswith('Howard Miller Student Center, '):
        s = s.split(', ', 1)[1] + ', Howard Miller Student Center'
    for room, building in [('Bly Hall', 'Daniel & Dorothy Spence Academic Center'), ('Stamm Hall', 'James Pedas Communication Center')]:
        if room in s and building not in s:
            s = s.replace(room, f'{room}, {building}')
    return s or 'Location not listed'

def get(url):
    if urlparse(url).netloc != 'www.thiel.edu':
        raise ValueError('Unexpected calendar host')
    response = requests.get(url, timeout=30, headers={'User-Agent': 'Thiel-TNotes-Calendar/1.0'})
    response.raise_for_status()
    return BeautifulSoup(response.text, 'html.parser')

def detail(soup, title, date, source):
    body = soup.select_one('.modal-body')
    if body is None or soup.select_one('.modal-title') is None or 'UNKNOWN EVENT' in soup.get_text():
        raise ValueError('Event detail structure missing or unknown event')
    title = clean(soup.select_one('.modal-title').get_text(' ', strip=True))
    stamp = body.select_one('.eventpagedt')
    time, order = ap_time(stamp.get_text(' ', strip=True) if stamp else '')
    is_all_day = bool(stamp and re.search(r'all.?day', stamp.get_text(), re.I))
    match = re.match(r'([A-Z]+)\s+vs\.?\s+(.+)', title)
    sport = SPORTS.get(match[1]) if match else None
    loc = body.select_one('.eventpagelocation')
    loc = location(loc.get_text(' ', strip=True) if loc else '', sport)
    # Only description content after the location and before contact/footer blocks.
    description = []
    links = []
    if body.select_one('.eventpagelocation'):
        for sibling in body.select_one('.eventpagelocation').next_siblings:
            if getattr(sibling, 'name', None) == 'hr' or (getattr(sibling, 'get', None) and 'nada' in sibling.get('class', [])):
                break
            if not getattr(sibling, 'find_all', None):
                continue
            if sibling.name not in ['img', 'script']:
                text = clean(sibling.get_text(' ', strip=True))
                if text:
                    description.append(text)
                for a in sibling.find_all('a', href=True):
                    url = urljoin(BASE, a['href'])
                    if urlparse(url).scheme in ['https', 'http', 'mailto']:
                        links.append({'label': clean(a.get_text(' ', strip=True)) or 'More information here', 'url': url})
    raw = ' '.join(description)
    warnings = []
    if sport:
        sentence = f'Thiel hosts {clean(match[2])} in {sport}.'
    else:
        # Conservative extraction: editorial rewriting requires human review.
        sentence = re.split(r'(?<=[.!?])\s+', raw)[0] if raw else 'Description not listed.'
        if re.match(r'(?i)(join|participate|come|register|you|your|pick up)\b', sentence) or len(sentence.split()) > 40:
            sentence = f'{title} is scheduled for the campus community.'
            warnings.append('Description needs editorial review; neutral placeholder used. See source description.')
        elif raw:
            warnings.append('Check extracted description for third person, AP style and concision.')
        if not raw:
            warnings.append('Missing description.')
        if sentence[-1:] not in '.!?':
            sentence += '.'
    for link in links:
        if link['label'] not in sentence:
            sentence += ' ' + link['label'].rstrip('.') + '.'
    if time is None and not is_all_day:
        warnings.append('Missing or unrecognized start time.')
    if loc == 'Location not listed':
        warnings.append('Missing location.')
    return dict(title=title, date=date.isoformat(), time=time, all_day=is_all_day, order=order, location=loc, description=sentence, links=links, source=source, source_description=raw, warnings=warnings)

def render(event):
    date = dt.date.fromisoformat(event['date'])
    when = 'all day' if event['all_day'] else event['time'] or 'time not listed'
    return f"**{event['title']}**  \n{MONTHS[date.month]} {date.day} at {when}  \n*{event['location']}*  \n{event['description']}"

DOMS_URL = BASE + '/jt/doms-calendar'

def parse_doms(soup, anchor):
    """Parse the rolling listing; infer its omitted year near today's date."""
    records = []
    blocks = re.split(r'<hr\b[^>]*>', str(soup), flags=re.I)
    for block in blocks:
        fragment = BeautifulSoup(block, 'html.parser')
        header = fragment.find('p')
        if not header or not header.find('strong'):
            continue
        title = header.find('strong').get_text(' ', strip=True)
        lines = [x.strip() for x in header.get_text('\n', strip=True).splitlines() if x.strip()]
        stamp = next((x for x in lines if re.match(r'[A-Za-z]+\.?\s+\d+\s+at\s+', x)), None)
        if not stamp:
            raise ValueError(f'Unrecognized listing date: {title}')
        m = re.match(r'([A-Za-z]+)\.?\s+(\d+)\s+at\s+(.+)', stamp)
        month = next((i for i in range(1, 13) if MONTHS[i].rstrip('.').lower() == m[1].lower()), None)
        if month is None:
            raise ValueError(f'Unrecognized month: {stamp}')
        candidates = []
        for year in [anchor.year-1, anchor.year, anchor.year+1]:
            try:
                candidates.append(dt.date(year, month, int(m[2])))
            except ValueError:
                pass
        date = min(candidates, key=lambda d: abs((d-anchor).days))
        loc = header.find('em')
        synthetic = BeautifulSoup('<h5 class="modal-title"></h5><div class="modal-body"><p class="eventpagedt"></p><p class="eventpagelocation"></p></div>', 'html.parser')
        synthetic.select_one('.modal-title').string = title
        synthetic.select_one('.eventpagedt').string = m[3]
        synthetic.select_one('.eventpagelocation').string = loc.get_text(' ', strip=True) if loc else ''
        for sibling in list(header.next_siblings):
            synthetic.select_one('.modal-body').append(sibling)
        records.append(detail(synthetic, title, date, DOMS_URL))
    if not records:
        raise ValueError('No event entries found on Dom’s calendar')
    return records

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', default='')
    parser.add_argument('--whole-list', action='store_true', help='Include every entry on Dom’s calendar')
    parser.add_argument('--days', type=int, default=10)
    parser.add_argument('--output', default='output')
    args = parser.parse_args()
    if not 1 <= args.days <= 31:
        parser.error('--days must be between 1 and 31')
    start = dt.date.fromisoformat(args.start) if args.start else dt.datetime.now(ZoneInfo('America/New_York')).date()
    events, failures, seen = [], [], set()
    today = dt.datetime.now(ZoneInfo('America/New_York')).date()
    dom_dates = set()
    try:
        listing = parse_doms(get(DOMS_URL), today)
        # Use the demonstrated date span; fall back outside it rather than guess coverage.
        first = min(dt.date.fromisoformat(e['date']) for e in listing)
        last = max(dt.date.fromisoformat(e['date']) for e in listing)
        dom_dates = {first + dt.timedelta(days=i) for i in range((last-first).days+1)}
        events = listing if args.whole_list else [e for e in listing if start <= dt.date.fromisoformat(e['date']) < start + dt.timedelta(days=args.days)]
        if args.whole_list:
            start = first
            args.days = (last-first).days + 1
    except Exception as exc:
        if args.whole_list:
            raise SystemExit(f'Cannot fetch the complete Dom’s calendar listing: {exc}')
        print(f'Dom’s calendar unavailable; using daily calendar: {exc}')
    for offset in range(0 if args.whole_list else args.days):
        date = start + dt.timedelta(days=offset)
        if date in dom_dates:
            continue
        url = f'{BASE}/calendar/day/{date:%Y/%m/%d}'
        day = get(url)
        if not day.select_one('a.calendar_event_title') and not re.search(r'\b0 events\b', day.get_text(' ', strip=True)):
            # Empty calendar dates still have a date heading; detect unexpected templates.
            if date.strftime('%B') not in day.get_text():
                raise ValueError(f'Unrecognized day page: {url}')
        for a in day.select('a.calendar_event_title'):
            source = urljoin(BASE, a['href'])
            key = (date.isoformat(), source)
            if key in seen:
                continue
            seen.add(key)
            slug = urlparse(source).path.split('/calendar/event/', 1)[-1].strip('/')
            try:
                events.append(detail(get(f'{BASE}/calendar/modal_content/{slug}'), a.get_text(), date, source))
            except Exception as exc:
                failures.append(f'{date}: {a.get_text(strip=True)} — {exc} ({source})')
    events.sort(key=lambda e: (e['date'], e['order'], e['title']))
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    copy = '\n\n'.join(render(e) for e in events) + '\n'
    (out / 't-notes-calendar.md').write_text(copy, encoding='utf-8')
    (out / 'events.json').write_text(json.dumps(events, indent=2, ensure_ascii=False), encoding='utf-8')
    review = ['# Calendar review', f'Period: {start} through {start + dt.timedelta(days=args.days-1)}', f'{len(events)} entries; {len(failures)} failed event requests.']
    for e in events:
        if e['warnings'] or e['links']:
            review += [f"\n## {e['date']} — {e['title']}", e['source']]
            review += ['- ' + w for w in e['warnings']]
            review += [f"- {l['label']}: {l['url']}" for l in e['links']]
            if e['warnings']:
                review += ['Source description: ' + (e['source_description'] or '(none)')]
    review += ['\n## Failed requests'] + (failures or ['None.'])
    (out / 'review.md').write_text('\n\n'.join(review), encoding='utf-8')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a', encoding='utf-8') as f:
            f.write(f'# T-Notes calendar\n{len(events)} entries. Download the t-notes-calendar artifact for copy, links and review notes.\n\n' + copy + '\n\n' + '\n\n'.join(review))
    print(f'Generated {len(events)} entries; {len(failures)} failures. Output: {out}')
    if failures:
        raise SystemExit('Some event details could not be fetched; review the partial output.')

if __name__ == '__main__':
    main()
