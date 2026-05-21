import os

# Optional: set CHROMIUM_PATH env var to point at a specific Chromium binary.
# Useful if Playwright's auto-downloaded browser isn't available.
# Example (Linux): export CHROMIUM_PATH=/opt/pw-browsers/chromium-1194/chrome-linux/chrome
# Leave unset to let Playwright use its own bundled browser (default for local installs).
CHROMIUM_PATH = os.environ.get('CHROMIUM_PATH') or None

FACULTY_WEBSITES_URL = 'https://cod.edu/faculty/websites/index.html'
FACULTY_LISTING_BASE = 'https://cod.edu/_showcase/faculty/index.html'
COURSE_CATALOG_BASE = 'https://selfserv.cod.edu/Student/Courses/Search'
COD_BASE_URL = 'https://cod.edu'

OUTPUT_DIR = 'output'

REQUEST_DELAY = (0.5, 1.5)  # (min, max) seconds between requests
REQUEST_TIMEOUT = 15
MAX_RETRIES = 3

HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': (
        'text/html,application/xhtml+xml,application/xml;'
        'q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
}
