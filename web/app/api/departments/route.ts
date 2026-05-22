import { NextResponse } from 'next/server';
import { getUniqueDepartments } from '@/lib/db';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const departments = getUniqueDepartments();
    return NextResponse.json(departments);
  } catch (err) {
    console.error('[api/departments]', err);
    return NextResponse.json([], { status: 500 });
  }
}
