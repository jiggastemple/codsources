import { streamText, tool } from 'ai';
import { anthropic } from '@ai-sdk/anthropic';
import { z } from 'zod';
import { embedAndSearch } from '@/lib/search';
import { getById, isDbReady } from '@/lib/db';
import type { FacultyRecord } from '@/lib/faculty';

export const runtime = 'nodejs';
export const maxDuration = 60;

function buildFacultyContext(records: FacultyRecord[]): string {
  return records
    .map(f => {
      const depts = f.departments.join(', ') || 'General Faculty';
      const subjects = [
        ...new Set(
          f.courses_taught.map(c => c.subject_name || c.subject_code).filter(Boolean)
        ),
      ]
        .slice(0, 5)
        .join(', ');
      const bioSnippet = f.bio ? f.bio.slice(0, 400) + (f.bio.length > 400 ? '…' : '') : '';
      return [
        `ID: ${f.id}`,
        `Name: ${f.name}`,
        `Title: ${f.title || 'Faculty'}`,
        `Departments: ${depts}`,
        subjects ? `Teaches: ${subjects}` : null,
        bioSnippet ? `Bio: ${bioSnippet}` : null,
      ]
        .filter(Boolean)
        .join('\n');
    })
    .join('\n\n---\n\n');
}

const SYSTEM = (context: string) => `\
You are an expert source finder for the Courier Student News at College of DuPage (COD). \
You help student journalists quickly find the right faculty expert to interview for their stories.

When a student describes their story or topic, recommend 2–4 faculty experts from the list below \
who would be ideal interview sources. ALWAYS call the show_sources tool first with your picks, \
then follow up with a brief explanation of why each person fits the story (2–3 sentences each). \
Be direct and journalistically minded — think like an editor.

If none of the available experts are a strong match, say so clearly and suggest the student \
contact the COD Communications office or reach out to the Courier faculty advisor.

AVAILABLE EXPERTS (retrieved for this query):
${context || '(No experts found — the database may need to be indexed. Run: npm run ingest)'}`;

export async function POST(req: Request) {
  if (!isDbReady()) {
    return Response.json(
      { error: 'Database not initialized. Run: npm run ingest' },
      { status: 503 },
    );
  }

  const { messages } = await req.json() as { messages: Array<{ role: string; content: string }> };

  // Embed the latest user message for retrieval
  const lastUser = [...messages].reverse().find(m => m.role === 'user');
  const query = lastUser?.content ?? '';
  const topFaculty = await embedAndSearch(query, 6);

  const result = streamText({
    model: anthropic('claude-sonnet-4-6'),
    system: SYSTEM(buildFacultyContext(topFaculty)),
    messages: messages as Parameters<typeof streamText>[0]['messages'],
    tools: {
      show_sources: tool({
        description:
          'Display structured faculty expert cards to the student. Call this before any text explanation.',
        parameters: z.object({
          sources: z.array(
            z.object({
              id: z.string().describe('Faculty ID from the AVAILABLE EXPERTS list'),
              relevance_note: z
                .string()
                .describe('One sentence: why this person is relevant to this specific story'),
            }),
          ),
        }),
        execute: async ({ sources }) => {
          // Enrich with full DB record so the UI has all contact details
          return sources.map(s => {
            const record = getById(s.id) ?? topFaculty.find(f => f.id === s.id);
            return { ...record, relevance_note: s.relevance_note };
          });
        },
      }),
    },
    maxSteps: 3,
  });

  return result.toDataStreamResponse();
}
