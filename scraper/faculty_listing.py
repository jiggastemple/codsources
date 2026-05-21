"""
Scrapes https://cod.edu/_showcase/faculty/index.html (paginated) using Playwright.

COD's server blocks plain requests — a real browser is required.
"""

import asyncio
import json
import os
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from config import FACULTY_LISTING_BASE, COD_BASE_URL, OUTPUT_DIR, CHROMIUM_PATH
from utils import extract_email, extract_phone, make_absolute

PAGE_LOAD_TIMEOUT = 20000


def parse_faculty_card(card_el):
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

    for sel in ['.faculty-name', '.name', 'h2', 'h3', 'h4',
                '[class*="name"]', 'strong', '.card-title']:
        el = card_el.select_one(sel)
        if el and el.get_text(strip=True):
            record['name'] = el.get_text(strip=True)
            break

    for sel in ['.faculty-title', '.title', '.position', '.job-title',
                '[class*="title"]', '[class*="position"]', '.card-subtitle']:
        el = card_el.select_one(sel)
        txt = el.get_text(strip=True) if el else ''
        if txt and txt != record['name']:
            record['title'] = txt
            break

    for sel in ['.department', '.dept', '[class*="department"]',
                '[class*="dept"]', '.division']:
        el = card_el.select_one(sel)
        if el and el.get_text(strip=True):
            record['departments'] = [el.get_text(strip=True)]
            break

    record['email'] = extract_email(card_el)
    record['phone'] = extract_phone(card_el.get_text())

    link = card_el.select_one('a[href]')
    if link:
        record['faculty_page_url'] = make_absolute(link['href'])

    img = card_el.select_one('img')
    if img and img.get('src'):
        record['photo_url'] = make_absolute(img['src'])

    for sel in ['.bio', '.excerpt', '.description', '.summary', 'p']:
        el = card_el.select_one(sel)
        if el:
            txt = el.get_text(strip=True)
            if len(txt) > 30 and txt != record['name']:
                record['bio'] = txt[:1000]
                break

    return record


def get_total_pages(soup):
    for sel in ['.pagination a', '.pager a', 'nav[aria-label*="page"] a',
                'a[href*="page="]']:
        links = soup.select(sel)
        page_nums = []
        for link in links:
            m = re.search(r'page=(\d+)', link.get('href', ''))
            if m:
                page_nums.append(int(m.group(1)))
            try:
                page_nums.append(int(link.get_text(strip=True)))
            except ValueError:
                pass
        if page_nums:
            return max(page_nums)

    m = re.search(r'(?:showing|page)\s+\d+\s+of\s+(\d+)', soup.get_text(), re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 1


def parse_page(html, page_num):
    soup = BeautifulSoup(html, 'lxml')
    records = []

    card_selectors = [
        '.faculty-card', '.faculty-item', '.faculty-profile',
        '[class*="faculty-card"]', '[class*="faculty-item"]',
        '.profile-card', '.staff-card', '.person-card',
        '.card', 'article', 'li.faculty',
    ]

    cards = []
    used_sel = None
    for sel in card_selectors:
        found = soup.select(sel)
        if found:
            cards = found
            used_sel = sel
            break

    if not cards:
        print(f"    [warning] No card selector matched on page {page_num} — extracting links")
        for a in soup.select('a[href*="/faculty/"]'):
            name = a.get_text(strip=True)
            href = make_absolute(a.get('href', ''))
            if name and href:
                records.append({
                    'name': name, 'title': '', 'departments': [],
                    'email': '', 'phone': '', 'office': '', 'bio': '',
                    'photo_url': '', 'faculty_page_url': href,
                    'source': ['faculty_listing'],
                })
        return records, get_total_pages(soup)

    print(f"    Selector '{used_sel}' → {len(cards)} cards")
    for card in cards:
        record = parse_faculty_card(card)
        if record['name']:
            records.append(record)

    return records, get_total_pages(soup)


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

            # Save raw HTML for the first page to help with selector debugging
            if current_page == 1:
                raw_path = os.path.join(OUTPUT_DIR, 'faculty_listing_page1.html')
                with open(raw_path, 'w', encoding='utf-8') as f:
                    f.write(html)
                await page.screenshot(path=os.path.join(OUTPUT_DIR, 'faculty_listing_page1.png'))
                print(f"    [saved raw HTML + screenshot → output/]")

            records, total_pages = parse_page(html, current_page)
            print(f"    {len(records)} records | total pages: {total_pages}")
            all_records.extend(records)

            if current_page >= total_pages:
                break
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
