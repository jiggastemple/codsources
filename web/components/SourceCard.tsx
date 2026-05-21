'use client';

import { useState, useEffect } from 'react';
import type { SourceResult } from '@/lib/faculty';

const SAVED_KEY = 'expert-sources-saved';

function getSaved(): string[] {
  try {
    return JSON.parse(localStorage.getItem(SAVED_KEY) ?? '[]');
  } catch {
    return [];
  }
}

function toggleSaved(id: string): boolean {
  const current = getSaved();
  const next = current.includes(id) ? current.filter(x => x !== id) : [...current, id];
  localStorage.setItem(SAVED_KEY, JSON.stringify(next));
  return next.includes(id);
}

const MAILTO_TEMPLATE = (name: string, email: string) => {
  const firstName = name.split(/[\s,]+/)[0];
  return `mailto:${email}?subject=Interview Request - Courier Student News&body=Hi ${firstName},%0A%0AMy name is [Your Name], and I'm a reporter with the Courier Student News at College of DuPage. I'm working on a story and would love to speak with you about your expertise.%0A%0AWould you be available for a brief 15–20 minute conversation this week?%0A%0AThank you,%0A[Your Name]%0ACourier Student News`;
};

export default function SourceCard({ source }: { source: SourceResult }) {
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setSaved(getSaved().includes(source.id));
  }, [source.id]);

  const handleSave = () => {
    const next = toggleSaved(source.id);
    setSaved(next);
  };

  const primaryDept = source.departments?.[0] ?? '';
  const extraDepts = (source.departments ?? []).slice(1);
  const subjects = [
    ...new Set(
      (source.courses_taught ?? [])
        .map(c => c.subject_name || c.subject_code)
        .filter(Boolean),
    ),
  ].slice(0, 4);

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      {/* Card header */}
      <div className="flex items-start gap-3 p-4 border-b border-gray-100">
        {source.photo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={source.photo_url}
            alt={source.name}
            className="w-14 h-14 rounded-full object-cover flex-shrink-0 bg-gray-100"
            onError={e => {
              (e.target as HTMLImageElement).style.display = 'none';
            }}
          />
        ) : (
          <div className="w-14 h-14 rounded-full flex-shrink-0 bg-cod-navy flex items-center justify-center text-white text-xl font-bold">
            {source.name.charAt(0)}
          </div>
        )}

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div>
              <h3 className="font-semibold text-gray-900 text-base leading-snug">
                {source.name}
              </h3>
              {source.title && (
                <p className="text-sm text-gray-500 mt-0.5">{source.title}</p>
              )}
            </div>
            <button
              onClick={handleSave}
              title={saved ? 'Remove from saved' : 'Save source'}
              className={`flex-shrink-0 p-1.5 rounded-lg transition-colors ${
                saved
                  ? 'text-cod-gold bg-yellow-50 hover:bg-yellow-100'
                  : 'text-gray-400 hover:text-cod-gold hover:bg-yellow-50'
              }`}
            >
              <BookmarkIcon filled={saved} />
            </button>
          </div>

          {/* Department chips */}
          <div className="flex flex-wrap gap-1 mt-2">
            {primaryDept && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-cod-navy text-white">
                {primaryDept}
              </span>
            )}
            {extraDepts.map(d => (
              <span
                key={d}
                className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700"
              >
                {d}
              </span>
            ))}
          </div>
        </div>
      </div>

      {/* Relevance note */}
      {source.relevance_note && (
        <div className="px-4 py-3 bg-amber-50 border-b border-amber-100 text-sm text-amber-900">
          <span className="font-medium">Why interview them: </span>
          {source.relevance_note}
        </div>
      )}

      {/* Subjects taught */}
      {subjects.length > 0 && (
        <div className="px-4 py-2.5 border-b border-gray-100">
          <p className="text-xs text-gray-500 mb-1.5 font-medium uppercase tracking-wide">Teaches</p>
          <div className="flex flex-wrap gap-1">
            {subjects.map(s => (
              <span
                key={s}
                className="px-2 py-0.5 rounded text-xs bg-gray-100 text-gray-600"
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Contact info */}
      <div className="px-4 py-3 space-y-1.5">
        {source.email && (
          <div className="flex items-center gap-2">
            <MailIcon />
            <a
              href={MAILTO_TEMPLATE(source.name, source.email)}
              className="text-sm text-cod-navy hover:underline truncate"
            >
              {source.email}
            </a>
            {source.email_inferred && (
              <span className="text-xs text-gray-400 flex-shrink-0">(inferred)</span>
            )}
          </div>
        )}
        {source.phone && (
          <div className="flex items-center gap-2">
            <PhoneIcon />
            <a href={`tel:${source.phone}`} className="text-sm text-gray-700 hover:underline">
              {source.phone}
            </a>
          </div>
        )}
        {source.office && (
          <div className="flex items-center gap-2">
            <OfficeIcon />
            <span className="text-sm text-gray-700">{source.office}</span>
          </div>
        )}
      </div>

      {/* Footer links */}
      {source.faculty_page_url && (
        <div className="px-4 py-2.5 border-t border-gray-100 bg-gray-50">
          <a
            href={source.faculty_page_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-cod-navy hover:underline font-medium"
          >
            View faculty profile →
          </a>
        </div>
      )}
    </div>
  );
}

function BookmarkIcon({ filled }: { filled: boolean }) {
  return (
    <svg className="w-4 h-4" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
    </svg>
  );
}

function PhoneIcon() {
  return (
    <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
    </svg>
  );
}

function OfficeIcon() {
  return (
    <svg className="w-3.5 h-3.5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
    </svg>
  );
}
