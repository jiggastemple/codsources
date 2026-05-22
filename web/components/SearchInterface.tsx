'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import type { FacultyRecord } from '@/lib/faculty';
import type { SourceResult } from '@/lib/faculty';
import SourceCard from './SourceCard';

const SAVED_KEY = 'expert-sources-saved';

function getSavedCount(): number {
  try {
    return (JSON.parse(localStorage.getItem(SAVED_KEY) ?? '[]') as string[]).length;
  } catch {
    return 0;
  }
}

export default function SearchInterface() {
  const [query, setQuery] = useState('');
  const [activeDept, setActiveDept] = useState<string | null>(null);
  const [departments, setDepartments] = useState<string[]>([]);
  const [results, setResults] = useState<SourceResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [savedCount, setSavedCount] = useState(0);
  const [dbReady, setDbReady] = useState<boolean | null>(null);
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load departments once
  useEffect(() => {
    fetch('/api/departments')
      .then(r => r.json())
      .then((depts: string[]) => setDepartments(depts))
      .catch(() => setDepartments([]));
    setSavedCount(getSavedCount());
  }, []);

  const doSearch = useCallback(async (q: string, dept: string | null) => {
    setIsLoading(true);
    setHasSearched(true);
    try {
      const params = new URLSearchParams({ limit: '12' });
      if (q.trim()) params.set('q', q.trim());
      if (dept) params.set('dept', dept);
      const res = await fetch(`/api/search?${params}`);
      if (!res.ok) throw new Error('Search failed');
      const data: FacultyRecord[] = await res.json();
      if (data && !('error' in data)) {
        setDbReady(true);
        setResults(data.map(r => ({ ...r, relevance_note: '' })));
      } else {
        setDbReady(false);
        setResults([]);
      }
    } catch {
      setResults([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Debounced search on query change
  useEffect(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current);
    if (!query.trim() && !activeDept) {
      setResults([]);
      setHasSearched(false);
      return;
    }
    debounceTimer.current = setTimeout(() => {
      doSearch(query, activeDept);
    }, 300);
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current);
    };
  }, [query, activeDept, doSearch]);

  const handleDeptClick = (dept: string) => {
    const next = activeDept === dept ? null : dept;
    setActiveDept(next);
  };

  const handleSavedChange = () => {
    setSavedCount(getSavedCount());
  };

  return (
    <div className="flex flex-col min-h-0 h-full">
      {/* Search bar area */}
      <div className="bg-white border-b border-gray-200 px-4 pt-5 pb-4 shadow-sm">
        <div className="max-w-3xl mx-auto">
          {/* Input */}
          <div className="relative">
            <div className="absolute inset-y-0 left-3 flex items-center pointer-events-none">
              <SearchIcon />
            </div>
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search by topic, name, or area of expertise…"
              className="w-full pl-10 pr-4 py-3 rounded-xl border border-gray-300 focus:outline-none focus:ring-2 focus:ring-cod-navy focus:border-transparent text-gray-900 placeholder-gray-400 text-base"
              autoFocus
            />
            {query && (
              <button
                onClick={() => { setQuery(''); inputRef.current?.focus(); }}
                className="absolute inset-y-0 right-3 flex items-center text-gray-400 hover:text-gray-600"
              >
                <XIcon />
              </button>
            )}
          </div>

          {/* Department chips */}
          {departments.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {departments.map(dept => (
                <button
                  key={dept}
                  onClick={() => handleDeptClick(dept)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    activeDept === dept
                      ? 'bg-cod-navy text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  }`}
                >
                  {dept}
                </button>
              ))}
            </div>
          )}

          {/* Status row */}
          <div className="mt-2 flex items-center justify-between text-xs text-gray-400">
            <span>
              {isLoading
                ? 'Searching…'
                : hasSearched
                  ? `${results.length} result${results.length !== 1 ? 's' : ''}${activeDept ? ` in ${activeDept}` : ''}`
                  : 'Type a topic or click a department to browse'}
            </span>
            {savedCount > 0 && (
              <span className="text-cod-gold font-medium">
                {savedCount} saved source{savedCount !== 1 ? 's' : ''}
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Results area */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 py-5">
          {/* DB not ready banner */}
          {dbReady === false && (
            <div className="rounded-xl bg-amber-50 border border-amber-200 p-4 text-sm text-amber-800 mb-4">
              <strong>Database not indexed yet.</strong> Run <code className="bg-amber-100 px-1 rounded">npm run ingest</code> in the <code className="bg-amber-100 px-1 rounded">web/</code> folder to load faculty data.
            </div>
          )}

          {/* Loading skeleton */}
          {isLoading && (
            <div className="grid gap-4 sm:grid-cols-2">
              {[...Array(4)].map((_, i) => (
                <div key={i} className="bg-white border border-gray-200 rounded-xl shadow-sm p-4 animate-pulse">
                  <div className="flex gap-3">
                    <div className="w-14 h-14 rounded-full bg-gray-200 flex-shrink-0" />
                    <div className="flex-1 space-y-2 pt-1">
                      <div className="h-4 bg-gray-200 rounded w-3/4" />
                      <div className="h-3 bg-gray-100 rounded w-1/2" />
                      <div className="h-3 bg-gray-100 rounded w-1/3" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Results grid */}
          {!isLoading && results.length > 0 && (
            <div
              className="grid gap-4 sm:grid-cols-2"
              onClick={handleSavedChange}
            >
              {results.map(r => (
                <SourceCard key={r.id} source={r} />
              ))}
            </div>
          )}

          {/* Empty state */}
          {!isLoading && hasSearched && results.length === 0 && dbReady !== false && (
            <div className="text-center py-16 text-gray-500">
              <div className="text-4xl mb-3">🔍</div>
              <p className="font-medium text-gray-700">No experts found</p>
              <p className="text-sm mt-1">Try a broader term or clear the department filter.</p>
            </div>
          )}

          {/* Welcome state */}
          {!isLoading && !hasSearched && (
            <div className="text-center py-16 text-gray-400">
              <div className="text-5xl mb-4">🎓</div>
              <p className="text-base font-medium text-gray-600">Find a faculty expert for your story</p>
              <p className="text-sm mt-2 max-w-xs mx-auto">
                Search by topic (e.g. &ldquo;climate change&rdquo;, &ldquo;mental health&rdquo;) or browse by department.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function SearchIcon() {
  return (
    <svg className="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 11A6 6 0 105 11a6 6 0 0012 0z" />
    </svg>
  );
}

function XIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}
