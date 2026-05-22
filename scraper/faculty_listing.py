"""
Scrapes https://cod.edu/_showcase/faculty/index.html (paginated) using Playwright.

COD's server blocks plain requests — a real browser is required.

Two-pass approach:
  Pass 1: scrape all paginated listing cards (name, title, dept, email, profile URL)
  Pass 2: visit each individual profile page to enrich bio and photo_url
           Skip with --skip-profiles for faster re-runs when only updating other sources.
"""

import asyncio
import json
import os
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from config import FACULTY_LISTING_BASE, COD_BASE_URL, OUTPUT_DIR, CHROMIUM_PATH
from utils import extract_email, extract_phone, make_absolute

PAGE_LOAD_TIMEOUT = 20000
PROFILE_CONCURRENCY = 5  # simultaneous profile page fetches


def parse_faculty_card(card_el):
    """
    Parse a single .FacultyCard element.

    COD card structure (confirmed from live HTML):
      .FacultyCard__name      → "Last, First" format
      .FacultyCard__title     → department/subject area (misleadingly named)
      .FacultyCard__position  → appears twice: role first, then email paragraph
      mailto: link            → confirmed COD email address
      <a href>                → link to individual faculty profile page
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

    # Profile URL — card may be wrapped in an <a> or contain one
    link_el = card_el if card_el.name == 'a' else card_el.select_one('a[href]')
    if link_el:
        href = link_el.get('href', '')
        if href and not href.startswith('mailto:') and not href.startswith('tel:'):
            record['faculty_page_url'] = make_absolute(href)

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


def scrape_profile_page(html):
    """
    Extract bio and photo_url from an individual faculty profile page.
    Returns a dict with only 'bio' and 'photo_url' so callers can merge selectively.
    """
    soup = BeautifulSoup(html, 'lxml')

    bio = ''
    for sel in [
        '.bio', '.biography', '.about-faculty', '.profile-bio', '.faculty-bio',
        '.wysiwyg-content', '.wysiwyg', '.FacultyProfile__bio', '.profile-content',
        'article', '.content', '#bio',
    ]:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(separator=' ', strip=True)
            if len(text) > 100:
                bio = text[:3000]
                break
    if not bio:
        paras = [
            p.get_text(strip=True)
            for p in soup.select('main p, #content p, .main-content p')
            if len(p.get_text(strip=True)) > 50
        ]
        if paras:
            bio = ' '.join(paras)[:3000]

    photo_url = ''
    for sel in [
        'img.faculty-photo', 'img.profile-photo', 'img.headshot',
        'img[class*="faculty"]', 'img[class*="profile"]',
        '.faculty-photo img', '.profile img',
        '.FacultyProfile__photo img', 'img.FacultyCard__photo',
    ]:
        el = soup.select_one(sel)
        if el and el.get('src'):
            src = make_absolute(el['src'])
            # Ignore tiny icons / placeholder images
            if src and 'placeholder' not in src.lower() and not src.endswith('.svg'):
                photo_url = src
                break

    return {'bio': bio, 'photo_url': photo_url}


async def enrich_with_profiles(context, records):
    """
    Second pass: visit each faculty_page_url to extract bio and photo_url.
    Uses a semaphore to limit concurrent browser pages.
    """
    to_enrich = [
        (i, r) for i, r in enumerate(records)
        if r.get('faculty_page_url') and not r.get('bio')
    ]
    if not to_enrich:
        print('  No profile URLs found on cards — skipping bio enrichment.')
        print('  (Check output/faculty_listing_page1.html: do .FacultyCard elements contain <a href>?)')
        return

    print(f'  Visiting {len(to_enrich)} profile pages to extract bio + photo '
          f'(concurrency={PROFILE_CONCURRENCY})...')

    sem = asyncio.Semaphore(PROFILE_CONCURRENCY)
    done_count = 0

    async def fetch_one(idx, record):
        nonlocal done_count
        async with sem:
            url = record['faculty_page_url']
            page = await context.new_page()
            try:
                await page.goto(url, wait_until='networkidle', timeout=PAGE_LOAD_TIMEOUT)
                html = await page.content()
                enrichment = scrape_profile_page(html)
                if enrichment['bio']:
                    records[idx]['bio'] = enrichment['bio']
                if enrichment['photo_url']:
                    records[idx]['photo_url'] = enrichment['photo_url']
            except Exception:
                pass
            finally:
                await page.close()
            done_count += 1
            if done_count % 200 == 0 or done_count == len(to_enrich):
                bio_n = sum(1 for r in records if r.get('bio'))
                print(f'    {done_count}/{len(to_enrich)} profiles fetched — {bio_n} with bio')
            await asyncio.sleep(0.3)

    await asyncio.gather(*[fetch_one(i, r) for i, r in to_enrich])

    bio_n = sum(1 for r in records if r.get('bio'))
    photo_n = sum(1 for r in records if r.get('photo_url'))
    print(f'  Profile enrichment complete: {bio_n} bios, {photo_n} photos')


async def run(skip_profiles=False):
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

        print(f'  Starting at: {FACULTY_LISTING_BASE}?page=1')

        # --- Pass 1: scrape listing cards ---
        while True:
            url = f'{FACULTY_LISTING_BASE}?page={current_page}'
            print(f'  Page {current_page}: {url}')

            try:
                await page.goto(url, wait_until='networkidle', timeout=PAGE_LOAD_TIMEOUT)
            except Exception as e:
                print(f'    ERROR loading page {current_page}: {e}')
                break

            html = await page.content()

            if current_page == 1:
                raw_path = os.path.join(OUTPUT_DIR, 'faculty_listing_page1.html')
                with open(raw_path, 'w', encoding='utf-8') as f:
                    f.write(html)
                await page.screenshot(path=os.path.join(OUTPUT_DIR, 'faculty_listing_page1.png'))
                print('    [saved raw HTML + screenshot → output/]')

            records = parse_page(html)
            print(f'    {len(records)} records')
            if not records:
                break
            all_records.extend(records)
            current_page += 1
            await asyncio.sleep(1.0)

        await page.close()

        # --- Pass 2: enrich with individual profile pages ---
        if not skip_profiles:
            await enrich_with_profiles(context, all_records)
        else:
            print('  [--skip-profiles] Skipping bio enrichment pass.')

        await browser.close()

    out_path = os.path.join(OUTPUT_DIR, 'faculty_listing.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(all_records, f, indent=2, ensure_ascii=False)
    print(f'\n  Saved {len(all_records)} records → {out_path}')
    return all_records


def scrape(skip_profiles=False):
    return asyncio.run(run(skip_profiles=skip_profiles))


if __name__ == '__main__':
    import sys
    _skip = '--skip-profiles' in sys.argv
    scrape(skip_profiles=_skip)
