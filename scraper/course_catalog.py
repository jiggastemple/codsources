"""
Scrapes https://selfserv.cod.edu/Student/Courses/Search using Playwright.

selfserv.cod.edu is an Ellucian Colleague Self-Service SPA (React). Simple HTTP
requests won't work — we need a real browser to let the JS render.

Strategy:
1. Open the course search page and wait for it to fully load.
2. Find the subject/department filter and collect all available subject codes.
3. For each subject, navigate to its filtered URL and scrape all course sections.
4. Extract: subject, course code, course name, instructor name(s).
5. Build a dict mapping instructor_name -> list of courses taught.

Run with:  python course_catalog.py
           python course_catalog.py --subjects ACCOU BIOL  (limit to specific subjects)
"""

import asyncio
import json
import os
import re
import sys
from playwright.async_api import async_playwright
from config import COURSE_CATALOG_BASE, OUTPUT_DIR, CHROMIUM_PATH

SCROLL_PAUSE = 1.5      # seconds to pause after each scroll
PAGE_LOAD_TIMEOUT = 30000  # ms


async def get_subject_codes(page):
    """
    Get all course subject codes from the Ellucian Self-Service subjects API.

    The course search SPA loads subjects via a background JSON API call.
    We intercept that response directly rather than trying to read the
    dynamically-rendered UI, which is empty on initial page load.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    subjects = []
    api_response = {}

    # Intercept the subjects API response as the page loads
    async def handle_response(response):
        if 'subjects' in response.url.lower() or 'catalog' in response.url.lower():
            try:
                data = await response.json()
                if isinstance(data, list) and data and 'code' in data[0]:
                    api_response['subjects'] = data
                elif isinstance(data, dict) and 'subjects' in data:
                    api_response['subjects'] = data['subjects']
            except Exception:
                pass

    page.on('response', handle_response)

    print("  Navigating to course search (watching for subjects API call)...")
    try:
        await page.goto(COURSE_CATALOG_BASE, wait_until='networkidle', timeout=PAGE_LOAD_TIMEOUT)
    except Exception as e:
        print(f"  Navigation warning: {e}")

    page.remove_listener('response', handle_response)
    await page.screenshot(path=os.path.join(OUTPUT_DIR, 'course_catalog_subjects.png'), full_page=True)

    if api_response.get('subjects'):
        raw = api_response['subjects']
        for s in raw:
            code = s.get('code', '').strip()
            name = s.get('description', s.get('name', '')).strip()
            if code:
                subjects.append({'code': code, 'name': name})
        print(f"  Found {len(subjects)} subjects via API interception")
        return subjects

    # Fallback: read subjects from the embedded JSON in the page HTML.
    # Ellucian embeds initial state as Ellucian.Course.SearchResult.jsonData = {...}
    content = await page.content()
    m = re.search(r'jsonData\s*=\s*(\{.*?\});', content, re.DOTALL)
    if m:
        try:
            import json as _json
            data = _json.loads(m.group(1))
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

    # Last resort: use the known COD department checkbox values from the faculty
    # listing page as subject code seeds. These are lowercase department slugs
    # but many match Ellucian subject codes (e.g. "accountancy" → "ACCOU").
    # We include a curated list of common COD subject codes as a reliable fallback.
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
        ('WELD', 'Welding'), ('WMST', 'Women\'s Studies'),
    ]
    subjects = [{'code': c, 'name': n} for c, n in fallback_subjects]
    print(f"  Using {len(subjects)} fallback subject codes")
    with open(os.path.join(OUTPUT_DIR, 'course_catalog_page.html'), 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Saved page HTML → {OUTPUT_DIR}/course_catalog_page.html")
    return subjects


async def scrape_subject(page, subject_code, subject_name, debug_api=False):
    """Scrape all course sections for one subject. Returns list of course dicts.

    Instructor data lives in Knockout.js virtual elements that are never stamped
    into the static DOM — we must intercept the background JSON API calls instead.
    DOM parsing is kept as a fallback to at least capture course titles/descriptions.
    """
    url = f"{COURSE_CATALOG_BASE}?subjects={subject_code}"
    print(f"    {subject_code} ({subject_name}): {url}")

    captured = {}
    debug_log = []  # populated when debug_api=True

    async def handle_response(response):
        rt = response.request.resource_type
        if rt not in ('xhr', 'fetch'):
            return
        resp_url = response.url
        ct = response.headers.get('content-type', '')
        status = response.status

        if debug_api:
            debug_log.append(f"  {status} [{rt}] {ct[:40]:40s}  {resp_url}")

        url_lower = resp_url.lower()
        # In debug mode accept any JSON response to find the right endpoint.
        # In normal mode filter to likely Ellucian API paths.
        url_ok = debug_api or any(
            kw in url_lower for kw in ('section', 'course', 'catalog', 'search')
        )
        if not url_ok or 'json' not in ct:
            return
        try:
            data = await response.json()
            if isinstance(data, list) and data and isinstance(data[0], dict):
                sample = str(data[0]).lower()
                if debug_api or any(
                    k in sample for k in ('faculty', 'instructor', 'section', 'coursename')
                ):
                    captured.setdefault('sections', []).extend(data)
                    if debug_api:
                        print(f"      [debug] captured list response ({len(data)} items) from {resp_url[:80]}")
            elif isinstance(data, dict):
                for key in ('Sections', 'sections', 'Courses', 'courses', 'Results', 'results'):
                    if key in data and isinstance(data[key], list):
                        captured.setdefault('sections', []).extend(data[key])
                        if debug_api:
                            print(f"      [debug] captured dict[{key!r}] ({len(data[key])} items) from {resp_url[:80]}")
                        break
        except Exception:
            pass

    page.on('response', handle_response)
    try:
        await page.goto(url, wait_until='networkidle', timeout=PAGE_LOAD_TIMEOUT)
    except Exception as e:
        print(f"      Navigation error: {e}")
    await asyncio.sleep(5)
    page.remove_listener('response', handle_response)

    if debug_api:
        log_path = os.path.join(OUTPUT_DIR, f'debug_api_{subject_code}.txt')
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(f"All XHR/fetch responses for subject {subject_code}:\n\n")
            f.write('\n'.join(debug_log) or '  (none captured)')
        print(f"      [debug] {len(debug_log)} XHR/fetch responses logged → {log_path}")

    courses = []

    if captured.get('sections'):
        for sec in captured['sections']:
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
                names = []
                for f in raw_faculty:
                    if isinstance(f, dict):
                        n = f.get('Name') or f.get('name') or f.get('InstructorName') or ''
                    else:
                        n = str(f)
                    if n:
                        names.append(n.strip())
                instructor = '; '.join(names)
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
        print(f"      API interception → {len(courses)} sections")
        return courses

    # Fallback: API interception captured nothing — parse DOM for course titles only.
    # Instructors are unavailable this way (they live in KO virtual elements).
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
    debug_api:      log all XHR/fetch URLs to output/debug_api_<SUBJ>.txt so you
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
