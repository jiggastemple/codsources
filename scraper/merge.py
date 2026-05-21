"""
Merges faculty records from all three scrapers into a single deduplicated JSON file.

Deduplication key: normalized name (lowercase, stripped of titles/punctuation).
When the same person appears in multiple sources, their records are merged with
the richest available data preferred (longest bio wins, first non-empty email wins, etc.)

Also attempts to infer missing COD emails from the pattern firstname.lastname@cod.edu
when a name is available but no email was found.

Output:
  output/faculty_merged.json   — array of unified faculty records
  output/data_quality.json     — stats on field completeness
"""

import json
import os
import re
from utils import normalize_name
from config import OUTPUT_DIR


def load_json(path, default=None):
    if default is None:
        default = []
    if not os.path.exists(path):
        print(f"  [skip] {path} not found")
        return default
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def infer_cod_email(name):
    """
    COD email pattern: firstname.lastname@cod.edu

    Handles both name formats found across sources:
      "Last, First"  (faculty listing cards)
      "First Last"   (faculty profile pages)
    """
    name = name.strip()
    if ',' in name:
        # "Last, First Middle" format
        parts = name.split(',', 1)
        last = re.sub(r'[^a-z]', '', parts[0].strip().lower())
        first = re.sub(r'[^a-z]', '', parts[1].strip().split()[0].lower())
    else:
        # "First Last" format
        parts = name.split()
        if len(parts) < 2:
            return ''
        first = re.sub(r'[^a-z]', '', parts[0].lower())
        last = re.sub(r'[^a-z]', '', parts[-1].lower())
    if first and last:
        return f"{first}.{last}@cod.edu"
    return ''


def merge_records(a, b):
    """Merge two records for the same person, preferring richer data."""
    merged = dict(a)

    for key in ['name', 'title', 'email', 'phone', 'office', 'faculty_page_url', 'photo_url']:
        if not merged.get(key) and b.get(key):
            merged[key] = b[key]

    # Bio: keep longest
    if len(b.get('bio', '')) > len(merged.get('bio', '')):
        merged['bio'] = b['bio']

    # Departments: union
    depts = list(merged.get('departments', []))
    for d in b.get('departments', []):
        if d and d not in depts:
            depts.append(d)
    merged['departments'] = depts

    # Courses: union
    courses = list(merged.get('courses_taught', []))
    for c in b.get('courses_taught', []):
        if c not in courses:
            courses.append(c)
    merged['courses_taught'] = courses

    # Sources: union
    sources = list(set(merged.get('source', []) + b.get('source', [])))
    merged['source'] = sources

    return merged


def merge_all():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    websites = load_json(os.path.join(OUTPUT_DIR, 'faculty_websites.json'))
    listing = load_json(os.path.join(OUTPUT_DIR, 'faculty_listing.json'))
    instructor_courses = load_json(os.path.join(OUTPUT_DIR, 'instructor_courses.json'), default={})

    print(f"\n[merge] Input counts:")
    print(f"  faculty_websites:  {len(websites)}")
    print(f"  faculty_listing:   {len(listing)}")
    print(f"  instructor names from course catalog: {len(instructor_courses)}")

    # Index all records by normalized name
    index = {}  # normalized_name -> record

    def add_record(record):
        key = normalize_name(record.get('name', ''))
        if not key:
            return
        if 'courses_taught' not in record:
            record['courses_taught'] = []
        if key in index:
            index[key] = merge_records(index[key], record)
        else:
            index[key] = dict(record)

    for r in websites:
        add_record(r)
    for r in listing:
        add_record(r)

    # Attach course data from course catalog
    for instructor_name, courses in instructor_courses.items():
        key = normalize_name(instructor_name)
        if key in index:
            existing_codes = {c.get('course_code') for c in index[key].get('courses_taught', [])}
            for c in courses:
                if c.get('course_code') not in existing_codes:
                    index[key]['courses_taught'].append(c)
                    existing_codes.add(c.get('course_code'))
        else:
            # Instructor from course catalog not found in faculty pages — add stub
            index[key] = {
                'name': instructor_name,
                'title': '',
                'departments': [],
                'email': '',
                'phone': '',
                'office': '',
                'bio': '',
                'photo_url': '',
                'faculty_page_url': '',
                'courses_taught': courses,
                'source': ['course_catalog'],
            }

    # Infer missing emails
    inferred_count = 0
    for key, record in index.items():
        if not record.get('email') and record.get('name'):
            inferred = infer_cod_email(record['name'])
            if inferred:
                record['email'] = inferred
                record['email_inferred'] = True
                inferred_count += 1
        else:
            record['email_inferred'] = False

    faculty = list(index.values())
    faculty.sort(key=lambda r: r.get('name', ''))

    # Add stable IDs
    for i, r in enumerate(faculty):
        slug = re.sub(r'[^a-z0-9]+', '-', normalize_name(r.get('name', f'unknown-{i}')))
        r['id'] = f"{slug}-{i}"

    # Save merged output
    out_path = os.path.join(OUTPUT_DIR, 'faculty_merged.json')
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(faculty, f, indent=2, ensure_ascii=False)

    # Data quality report
    total = len(faculty)
    fields = ['name', 'title', 'email', 'phone', 'office', 'bio', 'photo_url',
              'faculty_page_url', 'departments', 'courses_taught']

    quality = {}
    for field in fields:
        count = sum(1 for r in faculty if r.get(field))
        quality[field] = {'count': count, 'pct': round(100 * count / total, 1) if total else 0}

    quality['email_inferred'] = {
        'count': inferred_count,
        'pct': round(100 * inferred_count / total, 1) if total else 0,
    }
    quality['email_confirmed'] = {
        'count': sum(1 for r in faculty if r.get('email') and not r.get('email_inferred')),
        'pct': 0,
    }
    quality['email_confirmed']['pct'] = round(
        100 * quality['email_confirmed']['count'] / total, 1
    ) if total else 0

    quality_path = os.path.join(OUTPUT_DIR, 'data_quality.json')
    with open(quality_path, 'w', encoding='utf-8') as f:
        json.dump({'total_faculty': total, 'fields': quality}, f, indent=2)

    print(f"\n[merge] Results:")
    print(f"  Total faculty records:   {total}")
    print(f"  Emails confirmed:        {quality['email_confirmed']['count']} ({quality['email_confirmed']['pct']}%)")
    print(f"  Emails inferred:         {quality['email_inferred']['count']} ({quality['email_inferred']['pct']}%)")
    print(f"  With bio:                {quality['bio']['count']} ({quality['bio']['pct']}%)")
    print(f"  With department:         {quality['departments']['count']} ({quality['departments']['pct']}%)")
    print(f"  With courses:            {quality['courses_taught']['count']} ({quality['courses_taught']['pct']}%)")
    print(f"  With photo:              {quality['photo_url']['count']} ({quality['photo_url']['pct']}%)")
    print(f"\n  Saved → {out_path}")
    print(f"  Saved → {quality_path}")

    return faculty, quality


if __name__ == '__main__':
    merge_all()
