import { NextRequest, NextResponse } from 'next/server';
import { embedAndSearch } from '@/lib/search';
import { isDbReady, keywordSearch } from '@/lib/db';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  if (!isDbReady()) {
    return NextResponse.json({ error: 'db_not_ready' }, { status: 503 });
  }

  const { searchParams } = req.nextUrl;
  const q = searchParams.get('q') ?? '';
  const dept = searchParams.get('dept') ?? undefined;
  const limit = Math.min(parseInt(searchParams.get('limit') ?? '12', 10), 50);

  try {
    const results = process.env.OPENAI_API_KEY
      ? await embedAndSearch(q, limit, dept)
      : keywordSearch(q, limit, dept);
    return NextResponse.json(results);
  } catch (err) {
    console.error('[api/search]', err);
    return NextResponse.json({ error: 'Search failed' }, { status: 500 });
  }
}
