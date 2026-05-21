"""
Scrapes https://cod.edu/_showcase/faculty/index.html (paginated) using Playwright.

COD's server blocks plain requests — a real browser is required.
"""

import asyncio
import json
import os
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from config import FACULTY_LISTING_BASE, COD_BASE_URL, OUTPUT_DIR, CHROMIUM_PATH
from utils import extract_email, extract_phone, make_absolute

PAGE_LOAD_TIMEOUT = 20000


def parse_faculty_card(card_el):
    """
    Parse a single .FacultyCard element.

    COD card structure (confirmed from live HTML):
      .FacultyCard__name      → "Last, First" format
      .FacultyCard__title     → department/subject area (misleadingly named)
      .FacultyCard__position  → appears twice: role first, then email paragraph
      mailto: link            → confirmed COD email address
    """
    record = {
        'name': '',
        'title': '',
        'departments': [],
        'email': '',
        'phone': '',
        'office': '',
        'bio': '',
        'photo_url': '',
        'faculty_page_url': '',
        'source': ['faculty_listing'],
    }

    name_el = card_el.select_one('.FacultyCard__name')
    if name_el:
        record['name'] = name_el.get_text(strip=True)

    # FacultyCard__title holds the department/subject area
    dept_el = card_el.select_one('.FacultyCard__title')
    if dept_el:
        dept = dept_el.get_text(strip=True)
        if dept:
            record['departments'] = [dept]

    # FacultyCard__position appears twice: first = role, second = email line
    position_els = card_el.select('.FacultyCard__position')
    for el in position_els:
        text = el.get_text(strip=True)
        if not record['title'] and text and 'email' not in text.lower():
            record['title'] = text

    # Email is in a mailto: link inside the card
    record['email'] = extract_email(card_el)

    return record


def parse_page(html):
    soup = BeautifulSoup(html, 'lxml')
    cards = soup.select('.FacultyCard')
    records = []
    for card in cards:
        record = parse_faculty_card(card)
        if record['name']:
            records.append(record)
    return records


async def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_records = []

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
        current_page = 1

        print(f"  Starting at: {FACULTY_LISTING_BASE}?page=1")

        while True:
            url = f"{FACULTY_LISTING_BASE}?page={current_page}"
            print(f"  Page {current_page}: {url}")

            try:
                await page.goto(url, wait_until='networkidle', timeout=PAGE_LOAD_TIMEOUT)
            except Exception as e:
                print(f"    ERROR loading page {current_page}: {e}")
                break

            html = await page.content()

            if current_page == 1:
                raw_path = os.path.join(OUTPUT_DIR, 'faculty_listing_page1.html')
                with open(raw_path, 'w', encoding='utf-8') as f:
                    f.write(html)
                await page.screenshot(path=os.path.join(OUTPUT_DIR, 'faculty_listing_page1.png'))
                print(f"    [saved raw HTML + screenshot → output/]")

            records = parse_page(html)
            print(f"    {len(records)} records")
            if not records:
                # No cards on this page — we've gone past the last page
                break
            all_records.extend(records)
            current_page += 1
            await asyncio.sleep(1.0)

        await browser.close()

    out_path = os.path.join(OUTPUT_DIR, 'faculty_listing.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved {len(all_records)} records → {out_path}")
    return all_records


def scrape():
    return asyncio.run(run())


if __name__ == '__main__':
    scrape()
