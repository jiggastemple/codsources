"""
Scrapes https://selfserv.cod.edu/Student/Courses/Search using Playwright.

selfserv.cod.edu is an Ellucian Colleague Self-Service SPA (Knockout.js). Simple HTTP
requests won't work — we need a real browser to let the JS render.

Strategy:
1. Inject a JS interceptor that patches window.fetch and XMLHttpRequest so every JSON
   API response is captured into window.__codApiCapture before any SPA code runs.
2. Navigate to the course search page; collect subject codes from captured API responses.
3. For each subject, navigate to its filtered URL, wait for background API calls to finish,
   then read window.__codApiCapture for section/instructor data.
4. Build a dict mapping instructor_name -> list of courses taught.

Run with:  python course_catalog.py
           python course_catalog.py --subjects ACCOU BIOL  (limit to specific subjects)
           python course_catalog.py --debug-api ACCOU      (log all API calls for ACCOU)
"""

import asyncio
import json
import os
import re
import sys
from playwright.async_api import async_playwright
from config import COURSE_CATALOG_BASE, OUTPUT_DIR, CHROMIUM_PATH

PAGE_LOAD_TIMEOUT = 30000  # ms

# Injected into every page before SPA code runs. Patches fetch + XHR so every
# JSON response is stored in window.__codApiCapture for Python to read back.
_JS_INTERCEPTOR = """
window.__codApiCapture = { sections: [], log: [] };

const _origFetch = window.fetch;
window.fetch = async function(...args) {
    const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
    const resp = await _origFetch.apply(this, args);
    const clone = resp.clone();
    const ct = resp.headers.get('content-type') || '';
    window.__codApiCapture.log.push({ url, status: resp.status, ct, type: 'fetch' });
    if (ct.includes('json')) {
        try {
            const data = await clone.json();
            window.__codApiCapture.sections.push({ url, data });
        } catch(e) {}
    }
    return resp;
};

const _origOpen = XMLHttpRequest.prototype.open;
const _origSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function(method, url) {
    this._captureUrl = url;
    return _origOpen.apply(this, arguments);
};
XMLHttpRequest.prototype.send = function() {
    this.addEventListener('load', function() {
        const ct = this.getResponseHeader('content-type') || '';
        window.__codApiCapture.log.push({
            url: this._captureUrl, status: this.status, ct, type: 'xhr'
        });
        if (ct.includes('json') && this.responseText) {
            try {
                window.__codApiCapture.sections.push({
                    url: this._captureUrl,
                    data: JSON.parse(this.responseText)
                });
            } catch(e) {}
        }
    });
    return _origSend.apply(this, arguments);
};
"""


async def get_subject_codes(page):
    """
    Get all course subject codes from the Ellucian Self-Service subjects API.

    Reads from window.__codApiCapture (populated by _JS_INTERCEPTOR) after the
    subjects page loads. Falls back to embedded JSON then a hardcoded list.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("  Navigating to course search (watching for subjects API call)...")
    try:
        await page.goto(COURSE_CATALOG_BASE, wait_until='networkidle', timeout=PAGE_LOAD_TIMEOUT)
    except Exception as e:
        print(f"  Navigation warning: {e}")

    await page.screenshot(path=os.path.join(OUTPUT_DIR, 'course_catalog_subjects.png'), full_page=True)

    capture = await page.evaluate("() => window.__codApiCapture || {sections:[], log:[]}")
    subjects = []
    for item in capture.get('sections', []):
        data = item.get('data', {})
        # Ellucian may return [{"code":"ACCOU","description":"Accountancy"}, ...]
        # or {"subjects": [...]} or {"Subjects": [...]}
        if isinstance(data, list) and data and isinstance(data[0], dict):
            if 'code' in data[0] or 'Code' in data[0]:
                for s in data:
                    code = (s.get('code') or s.get('Code') or '').strip()
                    name = (s.get('description') or s.get('Description') or
                            s.get('name') or s.get('Name') or '').strip()
                    if code:
                        subjects.append({'code': code, 'name': name})
        elif isinstance(data, dict):
            for key in ('subjects', 'Subjects'):
                if key in data and isinstance(data[key], list):
                    for s in data[key]:
                        code = (s.get('code') or s.get('Code') or '').strip()
                        name = (s.get('description') or s.get('Description') or
                                s.get('name') or s.get('Name') or '').strip()
                        if code:
                            subjects.append({'code': code, 'name': name})
                    break

    if subjects:
        print(f"  Found {len(subjects)} subjects via JS intercept")
        return subjects

    # Fallback: read subjects from the embedded JSON in the page HTML.
    # Ellucian embeds initial state as Ellucian.Course.SearchResult.jsonData = {...}
    content = await page.content()
    m = re.search(r'jsonData\s*=\s*(\{.*?\});', content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            raw = data.get('subjects', [])
            for s in raw:
                code = s.get('code', '').strip()
                name = s.get('description', s.get('name', '')).strip()
                if code:
                    subjects.append({'code': code, 'name': name})
            if subjects:
                print(f"  Found {len(subjects)} subjects via embedded JSON")
                return subjects
        except Exception:
            pass

    # Last resort: curated list of known COD subject codes.
    print("  WARNING: API interception found no subjects. Using known COD subject codes.")
    fallback_subjects = [
        ('ACCOU', 'Accountancy'), ('ADMAP', 'Administrative Management'),
        ('ANTH', 'Anthropology'), ('ART', 'Art'), ('ARTH', 'Art History'),
        ('ASL', 'American Sign Language'), ('ASTR', 'Astronomy'),
        ('AUTO', 'Automotive Technology'), ('BIOL', 'Biology'),
        ('BSAD', 'Business Administration'), ('CHEM', 'Chemistry'),
        ('CHIN', 'Chinese'), ('CIS', 'Computer Information Systems'),
        ('CMET', 'Construction Management'), ('COMM', 'Communication'),
        ('CRIM', 'Criminal Justice'), ('CSCI', 'Computer Science'),
        ('DENT', 'Dental Hygiene'), ('ECON', 'Economics'),
        ('EDUC', 'Education'), ('ELEC', 'Electronics'),
        ('EMS', 'Emergency Medical Services'), ('ENGL', 'English'),
        ('ENGR', 'Engineering'), ('ESL', 'English as a Second Language'),
        ('FILM', 'Film'), ('FREN', 'French'), ('GEOG', 'Geography'),
        ('GEOL', 'Geology'), ('GERM', 'German'), ('HEAL', 'Health Education'),
        ('HIST', 'History'), ('HORT', 'Horticulture'),
        ('HOSP', 'Hospitality Management'), ('HUSR', 'Human Services'),
        ('ITAL', 'Italian'), ('JAPN', 'Japanese'), ('JOUR', 'Journalism'),
        ('KINE', 'Kinesiology'), ('LATN', 'Latin'), ('MATH', 'Mathematics'),
        ('MDIA', 'Media Arts'), ('MGMT', 'Management'), ('MKTG', 'Marketing'),
        ('MUSC', 'Music'), ('NURS', 'Nursing'), ('PHAR', 'Pharmacy Tech'),
        ('PHIL', 'Philosophy'), ('PHYS', 'Physics'), ('POLS', 'Political Science'),
        ('PSYC', 'Psychology'), ('RADT', 'Radiologic Technology'),
        ('READ', 'Reading'), ('RESP', 'Respiratory Care'),
        ('SIGN', 'Sign Language Interpreting'), ('SOCI', 'Sociology'),
        ('SPAN', 'Spanish'), ('SPED', 'Special Education'),
        ('SRGT', 'Surgical Technology'), ('THEA', 'Theatre'),
        ('WELD', 'Welding'), ('WMST', "Women's Studies"),
    ]
    subjects = [{'code': c, 'name': n} for c, n in fallback_subjects]
    print(f"  Using {len(subjects)} fallback subject codes")
    with open(os.path.join(OUTPUT_DIR, 'course_catalog_page.html'), 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Saved page HTML → {OUTPUT_DIR}/course_catalog_page.html")
    return subjects


async def scrape_subject(page, subject_code, subject_name, debug_api=False):
    """Scrape all course sections for one subject. Returns list of course dicts.

    Reads from window.__codApiCapture (populated by _JS_INTERCEPTOR). Instructor
    data lives in KO virtual elements never rendered into the DOM, so API
    interception is the only reliable source. DOM parsing is kept as a fallback
    to preserve at least course titles when no API data is available.
    """
    url = f"{COURSE_CATALOG_BASE}?subjects={subject_code}"
    print(f"    {subject_code} ({subject_name}): {url}")

    try:
        await page.goto(url, wait_until='networkidle', timeout=PAGE_LOAD_TIMEOUT)
    except Exception as e:
        print(f"      Navigation error: {e}")
    await asyncio.sleep(5)  # give KO time to finish all background API calls

    capture = await page.evaluate("() => window.__codApiCapture || {sections:[], log:[]}")

    if debug_api:
        log_path = os.path.join(OUTPUT_DIR, f'debug_api_{subject_code}.txt')
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(f"API calls captured for {subject_code}:\n\n")
            for entry in capture.get('log', []):
                f.write(
                    f"  {entry.get('status')} [{entry.get('type')}] "
                    f"{(entry.get('ct') or '')[:40]:40s}  {entry.get('url', '')}\n"
                )
            if not capture.get('log'):
                f.write("  (none — window.__codApiCapture.log is empty)\n")
        print(f"      [debug] {len(capture.get('log', []))} API calls logged → {log_path}")

    courses = []
    for item in capture.get('sections', []):
        data = item.get('data', {})
        if isinstance(data, dict):
            for key in ('Sections', 'sections', 'Courses', 'courses', 'Results', 'results'):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
        if not isinstance(data, list):
            continue
        for sec in data:
            if not isinstance(sec, dict):
                continue
            course_code = (
                sec.get('CourseId') or sec.get('CourseNumber') or
                sec.get('course_code') or sec.get('Number') or ''
            )
            course_name = (
                sec.get('CourseName') or sec.get('Title') or
                sec.get('course_name') or sec.get('Name') or ''
            )
            raw_faculty = (
                sec.get('Faculty') or sec.get('Instructors') or
                sec.get('faculty') or sec.get('instructors') or []
            )
            if isinstance(raw_faculty, list):
                names = [
                    (f.get('Name') or f.get('name') or f.get('InstructorName') or str(f)).strip()
                    if isinstance(f, dict) else str(f).strip()
                    for f in raw_faculty
                ]
                instructor = '; '.join(n for n in names if n)
            else:
                instructor = str(raw_faculty).strip()

            if course_code or course_name or instructor:
                courses.append({
                    'subject_code': subject_code,
                    'subject_name': subject_name,
                    'course_code': course_code,
                    'course_name': course_name,
                    'instructor': instructor,
                })

    if courses:
        print(f"      JS intercept → {len(courses)} sections")
        return courses

    # Fallback: DOM parse for course titles only (no instructor data available).
    print(f"      WARNING: no API data captured for {subject_code} — trying DOM fallback")
    content = await page.content()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, 'lxml')
    for li in soup.select('#course-resultul > li'):
        h3 = li.select_one('h3 span[id^="course-"]')
        if h3:
            text = h3.get_text(strip=True)
            m = re.match(r'^([A-Z]{2,6}-\d{3,4}[A-Z]?)\s+(.*)', text)
            if m:
                courses.append({
                    'subject_code': subject_code,
                    'subject_name': subject_name,
                    'course_code': m.group(1),
                    'course_name': m.group(2),
                    'instructor': '',
                })
    if courses:
        print(f"      DOM fallback → {len(courses)} courses (no instructors)")
    return courses


async def run(limit_subjects=None, debug_api=False):
    """
    limit_subjects: optional list of subject codes (e.g. ['ACCOU', 'BIOL'])
                    to restrict the scrape — useful for testing.
    debug_api:      log all API calls to output/debug_api_<SUBJ>.txt so you
                    can identify the real Ellucian API endpoint patterns.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_courses = []

    async with async_playwright() as pw:
        launch_kwargs = {'headless': True}
        if CHROMIUM_PATH:
            launch_kwargs['executable_path'] = CHROMIUM_PATH
        browser = await pw.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/120.0.0.0 Safari/537.36'
            ),
            viewport={'width': 1280, 'height': 900},
            ignore_https_errors=True,
        )
        page = await context.new_page()
        await page.add_init_script(_JS_INTERCEPTOR)

        print(f"\n[course_catalog] Collecting subject codes...")
        subjects = await get_subject_codes(page)

        if not subjects:
            print("  No subjects found — check output/course_catalog_page.html for page structure")
            await browser.close()
            return []

        if limit_subjects:
            subjects = [s for s in subjects if s['code'] in limit_subjects]
            print(f"  Limited to {len(subjects)} subjects: {[s['code'] for s in subjects]}")
        else:
            print(f"  Scraping all {len(subjects)} subjects...")

        for i, subj in enumerate(subjects):
            print(f"  [{i + 1}/{len(subjects)}]", end=' ')
            courses = await scrape_subject(page, subj['code'], subj['name'], debug_api=debug_api)
            all_courses.extend(courses)
            await asyncio.sleep(1.0)

        await browser.close()

    # Build instructor → courses mapping
    instructor_map = {}
    for c in all_courses:
        instructor = c['instructor']
        if not instructor:
            continue
        if instructor not in instructor_map:
            instructor_map[instructor] = []
        entry = {
            'subject_code': c['subject_code'],
            'subject_name': c['subject_name'],
            'course_code': c['course_code'],
            'course_name': c['course_name'],
        }
        if entry not in instructor_map[instructor]:
            instructor_map[instructor].append(entry)

    out_courses = os.path.join(OUTPUT_DIR, 'courses_raw.json')
    out_instructors = os.path.join(OUTPUT_DIR, 'instructor_courses.json')

    with open(out_courses, 'w', encoding='utf-8') as f:
        json.dump(all_courses, f, indent=2, ensure_ascii=False)

    with open(out_instructors, 'w', encoding='utf-8') as f:
        json.dump(instructor_map, f, indent=2, ensure_ascii=False)

    print(f"\n  {len(all_courses)} course sections scraped")
    print(f"  {len(instructor_map)} unique instructors found")
    print(f"  Saved → {out_courses}")
    print(f"  Saved → {out_instructors}")

    return instructor_map


def scrape(limit_subjects=None, debug_api=False):
    return asyncio.run(run(limit_subjects=limit_subjects, debug_api=debug_api))


if __name__ == '__main__':
    _debug = '--debug-api' in sys.argv
    _args = [a for a in sys.argv[1:] if not a.startswith('--')]
    scrape(limit_subjects=_args or None, debug_api=_debug)
