import os
import re
import time
import random
import requests
from bs4 import BeautifulSoup
from config import HEADERS, REQUEST_DELAY, REQUEST_TIMEOUT, MAX_RETRIES, OUTPUT_DIR


def get_session():
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def fetch_page(session, url, retries=MAX_RETRIES, save_as=None):
    """Fetch a URL with retries. Optionally save raw HTML to output/."""
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
            if save_as:
                os.makedirs(OUTPUT_DIR, exist_ok=True)
                path = os.path.join(OUTPUT_DIR, save_as)
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"    [saved raw HTML → {path}]")
            return html
        except requests.RequestException as e:
            print(f"    Attempt {attempt + 1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
    return None


def polite_delay():
    time.sleep(random.uniform(*REQUEST_DELAY))


def normalize_name(name):
    """Lowercase, strip titles and extra whitespace — used for deduplication."""
    name = name.lower().strip()
    name = re.sub(r'\s+', ' ', name)
    for title in ['dr.', 'prof.', 'professor', 'mr.', 'mrs.', 'ms.', 'ph.d.', 'phd', 'ph.d']:
        name = name.replace(title, '').strip()
    return name


def extract_email(soup):
    links = soup.select('a[href^="mailto:"]')
    if links:
        return links[0]['href'].replace('mailto:', '').strip().lower()
    # Fallback: look for @cod.edu pattern in text
    match = re.search(r'[\w.+-]+@cod\.edu', soup.get_text())
    return match.group(0).lower() if match else ''


def extract_phone(text):
    pattern = re.compile(r'\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}')
    phones = pattern.findall(text)
    return phones[0] if phones else ''


def make_absolute(url, base='https://cod.edu'):
    if not url:
        return ''
    if url.startswith('http'):
        return url
    if url.startswith('//'):
        return 'https:' + url
    return base.rstrip('/') + '/' + url.lstrip('/')
