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
    Navigate to the course search page and extract all subject codes from the
    filter UI. Falls back to reading them from the URL query string of filter links.
    """
    print("  Navigating to course search to collect subject codes...")
    await page.goto(COURSE_CATALOG_BASE, wait_until='networkidle', timeout=PAGE_LOAD_TIMEOUT)

    # Save a screenshot for inspection
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    await page.screenshot(path=os.path.join(OUTPUT_DIR, 'course_catalog_subjects.png'), full_page=True)

    subjects = []

    # Try: subject select/dropdown
    select_el = await page.query_selector(
        'select[id*="subject"], select[name*="subject"], select[aria-label*="subject" i]'
    )
    if select_el:
        options = await page.query_selector_all(
            'select[id*="subject"] option, select[name*="subject"] option'
        )
        for opt in options:
            value = await opt.get_attribute('value')
            text = await opt.inner_text()
            value = (value or '').strip()
            text = (text or '').strip()
            if value and value.lower() not in ('', 'all', 'select', 'any'):
                subjects.append({'code': value, 'name': text})
        if subjects:
            print(f"  Found {len(subjects)} subjects via <select>")
            return subjects

    # Try: links with ?subjects= in href
    links = await page.query_selector_all('a[href*="subjects="]')
    seen = set()
    for link in links:
        href = await link.get_attribute('href') or ''
        m = re.search(r'subjects=([A-Z0-9]+)', href)
        if m:
            code = m.group(1)
            if code not in seen:
                seen.add(code)
                text = await link.inner_text()
                subjects.append({'code': code, 'name': text.strip()})
    if subjects:
        print(f"  Found {len(subjects)} subjects via href links")
        return subjects

    # Try: checkboxes or filter items with subject codes (common in Colleague Self-Service)
    items = await page.query_selector_all(
        '[data-subject], [data-value*="subject"], '
        'input[value*="ACCOU"], input[value*="BIOL"], '  # probe for known codes
        'label[for*="subject"]'
    )
    for item in items:
        value = (await item.get_attribute('data-subject') or
                 await item.get_attribute('data-value') or
                 await item.get_attribute('value') or '')
        text = await item.inner_text()
        value = value.strip()
        if value and value not in seen:
            seen.add(value)
            subjects.append({'code': value, 'name': text.strip()})

    if not subjects:
        print("  WARNING: Could not find subject list from UI.")
        print("  Saving full page HTML for manual inspection...")
        content = await page.content()
        with open(os.path.join(OUTPUT_DIR, 'course_catalog_page.html'), 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"  Saved → {OUTPUT_DIR}/course_catalog_page.html")

    return subjects


async def scrape_subject(page, subject_code, subject_name):
    """Scrape all course sections for one subject. Returns list of course dicts."""
    url = f"{COURSE_CATALOG_BASE}?subjects={subject_code}"
    print(f"    {subject_code} ({subject_name}): {url}")

    try:
        await page.goto(url, wait_until='networkidle', timeout=PAGE_LOAD_TIMEOUT)
    except Exception as e:
        print(f"      Navigation error: {e}")
        return []

    courses = []
    # Scroll to trigger lazy-loaded content
    prev_count = 0
    for _ in range(20):
        await page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
        await asyncio.sleep(SCROLL_PAUSE)

        # Count current course items
        items = await page.query_selector_all(
            '.course-section, .section-listing, [class*="course-section"], '
            '[class*="section-result"], .search-result-item, article.course, '
            'tr.section-row, .availability-section'
        )
        if len(items) == prev_count and prev_count > 0:
            break  # no new items loaded
        prev_count = len(items)

    # Extract course data
    content = await page.content()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(content, 'lxml')

    # Try multiple Colleague Self-Service section patterns
    section_selectors = [
        '.course-section', '.section-listing', '.search-result-item',
        '[class*="course-section"]', '[class*="section-result"]',
        'tr.section-row', '.section-row', 'article.course',
        '.course-result', '.availability-section', '.catalog-course',
    ]

    sections = []
    used_sel = None
    for sel in section_selectors:
        found = soup.select(sel)
        if found:
            sections = found
            used_sel = sel
            break

    if not sections:
        # Fallback: look for instructor pattern in page text
        text = soup.get_text()
        instructors = re.findall(r'Instructor[:\s]+([A-Z][a-z]+,?\s+[A-Z][a-z]+)', text)
        for name in set(instructors):
            courses.append({
                'subject_code': subject_code,
                'subject_name': subject_name,
                'course_code': '',
                'course_name': '',
                'instructor': name.strip(),
            })
        if courses:
            print(f"      Fallback text extraction: {len(courses)} instructor mentions")
        return courses

    print(f"      Selector '{used_sel}' → {len(sections)} sections")

    for section in sections:
        text = section.get_text(separator=' ', strip=True)

        # Course code (e.g. "ACCOU-1101-001" or "ACCOU 1101")
        code_match = re.search(
            r'\b([A-Z]{2,6}[-\s]\d{3,4}(?:[-\s]\d{3})?)\b', text
        )
        course_code = code_match.group(1) if code_match else ''

        # Course name — look for a heading within the section
        name_el = section.select_one(
            'h2, h3, h4, .course-title, .section-title, [class*="course-name"], [class*="title"]'
        )
        course_name = name_el.get_text(strip=True) if name_el else ''

        # Instructor name
        instructor = ''
        for sel in [
            '.instructor', '[class*="instructor"]', '.faculty-name',
            'td.instructor', '[data-label="Instructor"]',
        ]:
            el = section.select_one(sel)
            if el:
                instructor = el.get_text(strip=True)
                break

        if not instructor:
            m = re.search(
                r'(?:Instructor|Faculty|Taught by)[:\s]+([A-Z][a-z]+(?:\s+[A-Z]\.?)?\s+[A-Z][a-z]+)',
                text
            )
            if m:
                instructor = m.group(1).strip()

        if course_code or course_name or instructor:
            courses.append({
                'subject_code': subject_code,
                'subject_name': subject_name,
                'course_code': course_code,
                'course_name': course_name,
                'instructor': instructor,
            })

    return courses


async def run(limit_subjects=None):
    """
    limit_subjects: optional list of subject codes (e.g. ['ACCOU', 'BIOL'])
                    to restrict the scrape — useful for testing.
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
            courses = await scrape_subject(page, subj['code'], subj['name'])
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


def scrape(limit_subjects=None):
    return asyncio.run(run(limit_subjects=limit_subjects))


if __name__ == '__main__':
    limit = sys.argv[1:] if len(sys.argv) > 1 else None
    scrape(limit_subjects=limit)
