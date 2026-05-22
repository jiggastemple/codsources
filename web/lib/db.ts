import path from 'path';
import type { FacultyRecord } from './faculty';

const DB_PATH = path.join(process.cwd(), 'data', 'faculty.db');

export interface DbRow {
  id: string;
  name: string;
  title: string;
  email: string;
  email_inferred: number;
  phone: string;
  office: string;
  departments: string;
  bio: string;
  photo_url: string;
  faculty_page_url: string;
  courses_taught: string;
  source: string;
  embedding: string | null;
}

export function parseRow(row: DbRow): FacultyRecord {
  return {
    id: row.id,
    name: row.name,
    title: row.title,
    email: row.email,
    email_inferred: Boolean(row.email_inferred),
    phone: row.phone,
    office: row.office,
    departments: safeParseJson(row.departments, []),
    bio: row.bio,
    photo_url: row.photo_url,
    faculty_page_url: row.faculty_page_url,
    courses_taught: safeParseJson(row.courses_taught, []),
    source: safeParseJson(row.source, []),
  };
}

function safeParseJson<T>(value: string, fallback: T): T {
  try {
    return JSON.parse(value);
  } catch {
    return fallback;
  }
}

// Lazy singleton — avoids importing better-sqlite3 at module load time in edge contexts
let _db: import('better-sqlite3').Database | null = null;

function getDb() {
  if (!_db) {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    const Database = require('better-sqlite3');
    _db = new Database(DB_PATH, { readonly: true }) as import('better-sqlite3').Database;
  }
  return _db;
}

export function isDbReady(): boolean {
  try {
    const db = getDb();
    const row = db.prepare('SELECT COUNT(*) as n FROM faculty').get() as { n: number };
    return row.n > 0;
  } catch {
    return false;
  }
}

export function hasEmbeddings(): boolean {
  try {
    const db = getDb();
    const row = db.prepare('SELECT COUNT(*) as n FROM faculty WHERE embedding IS NOT NULL').get() as { n: number };
    return row.n > 0;
  } catch {
    return false;
  }
}

export function getAllWithEmbeddings(): Array<DbRow & { embedding: string }> {
  return getDb()
    .prepare('SELECT * FROM faculty WHERE embedding IS NOT NULL')
    .all() as Array<DbRow & { embedding: string }>;
}

export function getById(id: string): FacultyRecord | null {
  try {
    const row = getDb().prepare('SELECT * FROM faculty WHERE id = ?').get(id) as DbRow | undefined;
    return row ? parseRow(row) : null;
  } catch {
    return null;
  }
}

export function keywordSearch(query: string, topK = 12, dept?: string): FacultyRecord[] {
  try {
    const db = getDb();
    const terms = query.toLowerCase().split(/\s+/).filter(t => t.length > 2);

    const rows = db
      .prepare('SELECT * FROM faculty WHERE name != "" ORDER BY name')
      .all() as DbRow[];

    const scored = rows
      .filter(row => !dept || safeParseJson<string[]>(row.departments, []).includes(dept))
      .map(row => {
        const text = [row.name, row.title, row.departments, row.bio, row.courses_taught]
          .join(' ')
          .toLowerCase();
        const score = terms.length
          ? terms.filter(t => text.includes(t)).length
          : 1; // no query → all match equally (for dept-only browse)
        return { row, score };
      });

    return scored
      .filter(s => s.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, topK)
      .map(s => parseRow(s.row));
  } catch {
    return [];
  }
}

export function getUniqueDepartments(): string[] {
  try {
    const rows = getDb()
      .prepare('SELECT departments FROM faculty WHERE departments != "[]" AND departments != ""')
      .all() as { departments: string }[];
    const depts = new Set<string>();
    for (const row of rows) {
      for (const d of safeParseJson<string[]>(row.departments, [])) {
        if (d) depts.add(d);
      }
    }
    return [...depts].sort();
  } catch {
    return [];
  }
}
