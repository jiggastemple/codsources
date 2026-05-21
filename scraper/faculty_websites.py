"""
Scrapes https://cod.edu/faculty/websites/index.html using Playwright.

COD's server blocks plain requests — a real browser is required.
For each faculty profile link found on the index page, we visit the
individual profile page and extract structured data.
"""

import asyncio
import json
import os
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from config import FACULTY_WEBSITES_URL, COD_BASE_URL, OUTPUT_DIR, CHROMIUM_PATH
from utils import extract_email, extract_phone, make_absolute, normalize_name

PAGE_LOAD_TIMEOUT = 20000


def parse_profile_page(html, url):
    soup = BeautifulSoup(html, 'lxml')
    record = {
        'name': '',
        'title': '',
        'departments': [],
        'email': '',
        'phone': '',
        'office': '',
        'bio': '',
        'photo_url': '',
        'faculty_page_url': url,
        'source': ['faculty_websites'],
    }

    for sel in ['h1.faculty-name', '.faculty-name', 'h1.page-title',
                '#content h1', 'main h1', 'h1', '.profile-name']:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            record['name'] = el.get_text(strip=True)
            break

    for sel in ['.faculty-title', '.job-title', '.position-title',
                '.title', '.profile-title', 'h2.subtitle', 'h2', 'h3']:
        el = soup.select_one(sel)
        txt = el.get_text(strip=True) if el else ''
        if txt and txt != record['name']:
            record['title'] = txt
            break

    for sel in ['.department', '.dept', '[class*="department"]',
                '[class*="dept"]', '.division']:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            record['departments'] = [el.get_text(strip=True)]
            break

    record['email'] = extract_email(soup)
    record['phone'] = extract_phone(soup.get_text())

    for el in soup.find_all(string=lambda t: t and 'office' in t.lower()):
        sibling = el.parent.find_next_sibling()
        if sibling:
            record['office'] = sibling.get_text(strip=True)
            break

    bio_candidates = []
    for sel in ['.bio', '.biography', '.about-faculty', '.profile-bio',
                '.faculty-bio', 'article', '.content', '.wysiwyg', '#bio']:
        el = soup.select_one(sel)
        if el:
            text = el.get_text(separator=' ', strip=True)
            if len(text) > 100:
                bio_candidates.append(text)
    if bio_candidates:
        record['bio'] = max(bio_candidates, key=len)[:3000]
    else:
        paras = [p.get_text(strip=True) for p in soup.select('main p, #content p')
                 if len(p.get_text(strip=True)) > 50]
        record['bio'] = ' '.join(paras)[:3000]

    for sel in ['img.faculty-photo', 'img.profile-photo', 'img.headshot',
                'img[class*="faculty"]', 'img[class*="profile"]',
                '.faculty-photo img', '.profile img']:
        el = soup.select_one(sel)
        if el and el.get('src'):
            record['photo_url'] = make_absolute(el['src'])
            break

    return record


async def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    records = []

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

        print(f"  Navigating to index: {FACULTY_WEBSITES_URL}")
        try:
            await page.goto(FACULTY_WEBSITES_URL, wait_until='networkidle',
                            timeout=PAGE_LOAD_TIMEOUT)
        except Exception as e:
            print(f"  ERROR loading index page: {e}")
            await browser.close()
            return []

        html = await page.content()
        # Save raw HTML for selector debugging
        with open(os.path.join(OUTPUT_DIR, 'faculty_websites_index.html'), 'w', encoding='utf-8') as f:
            f.write(html)
        await page.screenshot(path=os.path.join(OUTPUT_DIR, 'faculty_websites_index.png'))
        print(f"    [saved raw HTML + screenshot → output/]")

        soup = BeautifulSoup(html, 'lxml')
        profile_links = []

        for sel in ['a[href*="/faculty/"][href$=".html"]',
                    'a[href*="/faculty/websites/"]',
                    '.faculty-list a', '.faculty-listing a',
                    '#content a[href*="/faculty/"]',
                    'main a[href*="/faculty/"]']:
            found = soup.select(sel)
            if found:
                print(f"    Selector '{sel}' → {len(found)} links")
                profile_links = found
                break

        if not profile_links:
            profile_links = [a for a in soup.find_all('a', href=True)
                             if '/faculty/' in a['href'] and a.get_text(strip=True)]
            print(f"    Fallback: {len(profile_links)} /faculty/ links")

        seen = set()
        unique_links = []
        for a in profile_links:
            href = make_absolute(a.get('href', ''))
            if href and href not in seen:
                seen.add(href)
                unique_links.append((href, a.get_text(strip=True)))

        print(f"    {len(unique_links)} unique profile URLs found")

        for i, (url, link_text) in enumerate(unique_links):
            print(f"    [{i + 1}/{len(unique_links)}] {link_text}")
            try:
                await page.goto(url, wait_until='networkidle', timeout=PAGE_LOAD_TIMEOUT)
                profile_html = await page.content()
                record = parse_profile_page(profile_html, url)
                if not record['name']:
                    record['name'] = link_text
                records.append(record)
            except Exception as e:
                print(f"      Error fetching {url}: {e}")
            await asyncio.sleep(0.5)

        await browser.close()

    out_path = os.path.join(OUTPUT_DIR, 'faculty_websites.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved {len(records)} records → {out_path}")
    return records


def scrape():
    return asyncio.run(run())


if __name__ == '__main__':
    scrape()
