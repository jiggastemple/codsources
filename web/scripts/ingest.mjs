/**
 * Ingests scraper/output/faculty_merged.json into data/faculty.db.
 * Optionally generates OpenAI embeddings if OPENAI_API_KEY is set.
 *
 * Usage:
 *   npm run ingest
 *   OPENAI_API_KEY=sk-... npm run ingest
 */

import Database from 'better-sqlite3';
import { readFileSync, mkdirSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const WEB_ROOT = join(__dirname, '..');
const FACULTY_PATH = join(WEB_ROOT, '../scraper/output/faculty_merged.json');
const DB_DIR = join(WEB_ROOT, 'data');
const DB_PATH = join(DB_DIR, 'faculty.db');

// --- Load faculty data ---
if (!existsSync(FACULTY_PATH)) {
  console.error(`\n[ingest] ERROR: ${FACULTY_PATH} not found.`);
  console.error('  Run the scraper first:  cd ../scraper && python3 run.py\n');
  process.exit(1);
}

const faculty = JSON.parse(readFileSync(FACULTY_PATH, 'utf-8'));
console.log(`[ingest] Loaded ${faculty.length} records from faculty_merged.json`);

// --- Setup DB ---
mkdirSync(DB_DIR, { recursive: true });
const db = new Database(DB_PATH);
db.pragma('journal_mode = WAL');

db.exec(`
  CREATE TABLE IF NOT EXISTS faculty (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL DEFAULT '',
    title            TEXT NOT NULL DEFAULT '',
    email            TEXT NOT NULL DEFAULT '',
    email_inferred   INTEGER NOT NULL DEFAULT 0,
    phone            TEXT NOT NULL DEFAULT '',
    office           TEXT NOT NULL DEFAULT '',
    departments      TEXT NOT NULL DEFAULT '[]',
    bio              TEXT NOT NULL DEFAULT '',
    photo_url        TEXT NOT NULL DEFAULT '',
    faculty_page_url TEXT NOT NULL DEFAULT '',
    courses_taught   TEXT NOT NULL DEFAULT '[]',
    source           TEXT NOT NULL DEFAULT '[]',
    embedding        TEXT
  )
`);

// --- Insert records ---
const insert = db.prepare(`
  INSERT OR REPLACE INTO faculty
    (id, name, title, email, email_inferred, phone, office, departments,
     bio, photo_url, faculty_page_url, courses_taught, source)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`);

const insertAll = db.transaction(records => {
  for (const f of records) {
    insert.run(
      f.id || `unknown-${Math.random()}`,
      f.name || '',
      f.title || '',
      f.email || '',
      f.email_inferred ? 1 : 0,
      f.phone || '',
      f.office || '',
      JSON.stringify(f.departments || []),
      f.bio || '',
      f.photo_url || '',
      f.faculty_page_url || '',
      JSON.stringify(f.courses_taught || []),
      JSON.stringify(f.source || []),
    );
  }
});

insertAll(faculty);
console.log(`[ingest] Inserted ${faculty.length} records into ${DB_PATH}`);

// --- Embeddings ---
const OPENAI_API_KEY = process.env.OPENAI_API_KEY;
if (!OPENAI_API_KEY) {
  console.log('\n[ingest] OPENAI_API_KEY not set — skipping embeddings.');
  console.log('  Semantic search will fall back to keyword search.');
  console.log('  To enable: OPENAI_API_KEY=sk-... npm run ingest\n');
  process.exit(0);
}

function buildText(f) {
  const parts = [];
  if (f.name) parts.push(f.name);
  if (f.title) parts.push(f.title);
  if (f.departments?.length) parts.push('Department: ' + f.departments.join(', '));
  if (f.bio) parts.push(f.bio.slice(0, 600));
  const courses = (f.courses_taught || [])
    .map(c => c.course_name || c.subject_name)
    .filter(Boolean)
    .slice(0, 10)
    .join(', ');
  if (courses) parts.push('Courses: ' + courses);
  return parts.join('. ');
}

const texts = faculty.map(buildText);
const ids = faculty.map(f => f.id);
const BATCH = 100;
const updateEmb = db.prepare('UPDATE faculty SET embedding = ? WHERE id = ?');

console.log(`[ingest] Generating embeddings (${texts.length} records, batch size ${BATCH})...`);

for (let i = 0; i < texts.length; i += BATCH) {
  const batchTexts = texts.slice(i, i + BATCH);
  const batchIds = ids.slice(i, i + BATCH);
  const batchNum = Math.floor(i / BATCH) + 1;
  const totalBatches = Math.ceil(texts.length / BATCH);

  process.stdout.write(`  [${batchNum}/${totalBatches}] embedding ${batchTexts.length} records... `);

  const res = await fetch('https://api.openai.com/v1/embeddings', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${OPENAI_API_KEY}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ model: 'text-embedding-3-small', input: batchTexts }),
  });

  if (!res.ok) {
    const body = await res.text();
    console.error(`\nOpenAI error ${res.status}: ${body}`);
    process.exit(1);
  }

  const json = await res.json();
  const saveBatch = db.transaction(() => {
    for (let j = 0; j < json.data.length; j++) {
      updateEmb.run(JSON.stringify(json.data[j].embedding), batchIds[j]);
    }
  });
  saveBatch();
  console.log('done');
}

console.log(`\n[ingest] Complete. ${faculty.length} records with embeddings in ${DB_PATH}`);
db.close();
