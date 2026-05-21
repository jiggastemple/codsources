"""
Entry point for the COD Expert Sources scraper.

Usage:
  python run.py                     # Run all scrapers
  python run.py --skip-courses      # Skip the slow Playwright course catalog scrape
  python run.py --courses-only      # Only scrape the course catalog, then merge
  python run.py --subjects ACCOU BIOL  # Limit course catalog to specific subjects (for testing)
  python run.py --merge-only        # Re-run merge.py on existing output files
  python run.py --debug-api --subjects ACCOU  # Log all API calls for one subject to diagnose 0-result issues

All output files are written to the ./output/ directory.
Raw HTML pages are saved alongside JSON so you can inspect selectors if data looks wrong.
"""

import sys
import os
import time


def print_banner(text):
    bar = '=' * 60
    print(f"\n{bar}")
    print(f"  {text}")
    print(bar)


def main():
    args = sys.argv[1:]
    skip_faculty_websites = '--skip-faculty-websites' in args
    skip_faculty_listing  = '--skip-faculty-listing' in args
    skip_courses          = '--skip-courses' in args or '--merge-only' in args
    courses_only          = '--courses-only' in args
    merge_only            = '--merge-only' in args
    debug_api             = '--debug-api' in args

    limit_subjects = None
    if '--subjects' in args:
        idx = args.index('--subjects')
        limit_subjects = [a for a in args[idx + 1:] if not a.startswith('--')]

    os.makedirs('output', exist_ok=True)
    start = time.time()

    # --- Faculty Websites ---
    if not courses_only and not merge_only and not skip_faculty_websites:
        print_banner("Scraper 1/3: Faculty Websites (cod.edu/faculty/websites/)")
        try:
            from faculty_websites import scrape as scrape_websites
            records = scrape_websites()
            print(f"  Done. {len(records)} records.")
        except Exception as e:
            print(f"  ERROR in faculty_websites scraper: {e}")
            import traceback; traceback.print_exc()

    # --- Faculty Listing ---
    if not courses_only and not merge_only and not skip_faculty_listing:
        print_banner("Scraper 2/3: Faculty Listing (cod.edu/_showcase/faculty/)")
        try:
            from faculty_listing import scrape as scrape_listing
            records = scrape_listing()
            print(f"  Done. {len(records)} records.")
        except Exception as e:
            print(f"  ERROR in faculty_listing scraper: {e}")
            import traceback; traceback.print_exc()

    # --- Course Catalog ---
    if not skip_courses:
        print_banner("Scraper 3/3: Course Catalog (selfserv.cod.edu) — Playwright")
        print("  Note: This requires Playwright Chromium. If not installed, run:")
        print("    pip install playwright && playwright install chromium")
        try:
            from course_catalog import scrape as scrape_courses
            instructor_map = scrape_courses(limit_subjects=limit_subjects, debug_api=debug_api)
            print(f"  Done. {len(instructor_map)} instructors mapped.")
        except ImportError:
            print("  WARNING: playwright not installed — skipping course catalog.")
            print("  Install with: pip install playwright && playwright install chromium")
        except Exception as e:
            print(f"  ERROR in course_catalog scraper: {e}")
            import traceback; traceback.print_exc()

    # --- Merge ---
    print_banner("Merging all data sources")
    try:
        from merge import merge_all
        faculty, quality = merge_all()
    except Exception as e:
        print(f"  ERROR in merge: {e}")
        import traceback; traceback.print_exc()
        faculty, quality = [], {}

    elapsed = time.time() - start

    # --- Summary ---
    print_banner("Scrape Complete")
    total = quality.get('total_faculty', len(faculty))
    fields = quality.get('fields', {})

    print(f"\n  Total faculty records:   {total}")
    if fields:
        print(f"  With confirmed email:    {fields.get('email_confirmed', {}).get('count', '?')} "
              f"({fields.get('email_confirmed', {}).get('pct', '?')}%)")
        print(f"  With inferred email:     {quality.get('fields', {}).get('email_inferred', {}).get('count', '?')} "
              f"({quality.get('fields', {}).get('email_inferred', {}).get('pct', '?')}%)")
        print(f"  With bio:                {fields.get('bio', {}).get('count', '?')} "
              f"({fields.get('bio', {}).get('pct', '?')}%)")
        print(f"  With courses:            {fields.get('courses_taught', {}).get('count', '?')} "
              f"({fields.get('courses_taught', {}).get('pct', '?')}%)")
        print(f"  With department:         {fields.get('departments', {}).get('count', '?')} "
              f"({fields.get('departments', {}).get('pct', '?')}%)")
    print(f"\n  Time elapsed: {elapsed:.1f}s")
    print(f"\n  Output files in ./output/:")
    for fname in sorted(os.listdir('output')):
        fpath = os.path.join('output', fname)
        size_kb = os.path.getsize(fpath) / 1024
        print(f"    {fname:<40} {size_kb:>7.1f} KB")

    print(f"\n  Next steps:")
    print(f"  1. Review output/faculty_merged.json — spot-check 10–20 records")
    print(f"  2. Check output/data_quality.json for field completeness stats")
    print(f"  3. If emails are missing, check output/faculty_websites_index.html")
    print(f"     and output/faculty_listing_page1.html to inspect selector targets")
    print(f"  4. If course data is missing, check output/course_catalog_page.html")
    print(f"     and output/course_catalog_subjects.png for page structure\n")


if __name__ == '__main__':
    main()
