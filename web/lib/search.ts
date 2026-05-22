import { getAllWithEmbeddings, parseRow, keywordSearch } from './db';
import type { FacultyRecord } from './faculty';

function cosine(a: number[], b: number[]): number {
  let dot = 0, normA = 0, normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return normA && normB ? dot / (Math.sqrt(normA) * Math.sqrt(normB)) : 0;
}

// In-memory index built once per process
let index: Array<{ record: FacultyRecord; vec: number[] }> | null = null;

function getIndex() {
  if (!index) {
    const rows = getAllWithEmbeddings();
    index = rows.map(row => ({
      record: parseRow(row),
      vec: JSON.parse(row.embedding) as number[],
    }));
  }
  return index;
}

export function semanticSearch(queryEmbedding: number[], topK = 6): FacultyRecord[] {
  const idx = getIndex();
  return idx
    .map(({ record, vec }) => ({ record, score: cosine(queryEmbedding, vec) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, topK)
    .map(s => s.record);
}

export async function embedAndSearch(query: string, topK = 12, dept?: string): Promise<FacultyRecord[]> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return keywordSearch(query, topK, dept);
  }

  // For department-only browsing (no query text), skip embedding and use keyword path
  if (!query.trim()) {
    return keywordSearch('', topK, dept);
  }

  try {
    const res = await fetch('https://api.openai.com/v1/embeddings', {
      method: 'POST',
      headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model: 'text-embedding-3-small', input: query }),
    });
    if (!res.ok) throw new Error(`OpenAI ${res.status}`);
    const data = await res.json() as { data: Array<{ embedding: number[] }> };
    const results = semanticSearch(data.data[0].embedding, dept ? topK * 3 : topK);
    // Apply department filter after semantic retrieval
    const filtered = dept ? results.filter(r => r.departments.includes(dept)) : results;
    return filtered.slice(0, topK);
  } catch (err) {
    console.error('[search] embedding failed, falling back to keyword search:', err);
    return keywordSearch(query, topK, dept);
  }
}
