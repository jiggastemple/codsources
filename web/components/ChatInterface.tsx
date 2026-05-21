'use client';

import { useChat } from 'ai/react';
import { useEffect, useRef, useState } from 'react';
import MessageList from './MessageList';

const SUGGESTIONS = [
  'Mental health resources on campus',
  'AI and technology in education',
  'Climate change and sustainability',
  'Immigration policy impacts',
  'Healthcare access for students',
  'Campus budget and financial aid',
];

const SAVED_KEY = 'expert-sources-saved';

function getSavedCount(): number {
  try {
    return JSON.parse(localStorage.getItem(SAVED_KEY) ?? '[]').length;
  } catch {
    return 0;
  }
}

export default function ChatInterface({ dbReady }: { dbReady: boolean }) {
  const { messages, input, handleInputChange, handleSubmit, isLoading, error } = useChat({
    api: '/api/chat',
  });
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [savedCount, setSavedCount] = useState(0);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  // Track saved sources count
  useEffect(() => {
    setSavedCount(getSavedCount());
    const onStorage = () => setSavedCount(getSavedCount());
    window.addEventListener('storage', onStorage);
    // Also poll since localStorage changes within the same tab don't fire storage event
    const interval = setInterval(() => setSavedCount(getSavedCount()), 1000);
    return () => {
      window.removeEventListener('storage', onStorage);
      clearInterval(interval);
    };
  }, []);

  const sendSuggestion = (text: string) => {
    handleInputChange({ target: { value: text } } as React.ChangeEvent<HTMLTextAreaElement>);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (input.trim() && !isLoading) {
        handleSubmit(e as unknown as React.FormEvent);
      }
    }
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex flex-col h-full">
      {/* Saved sources badge */}
      {savedCount > 0 && (
        <div className="flex-shrink-0 px-4 py-2 bg-amber-50 border-b border-amber-200 flex items-center gap-2 text-sm text-amber-800">
          <BookmarkIcon />
          <span>{savedCount} source{savedCount !== 1 ? 's' : ''} saved</span>
          <button
            onClick={() => {
              localStorage.removeItem(SAVED_KEY);
              setSavedCount(0);
            }}
            className="ml-auto text-xs text-amber-600 hover:underline"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto px-4 py-6">
        {isEmpty ? (
          <EmptyState />
        ) : (
          <div className="max-w-3xl mx-auto">
            <MessageList messages={messages} isLoading={isLoading} />
            {error && (
              <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-sm text-red-700">
                {error.message || 'Something went wrong. Please try again.'}
              </div>
            )}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Suggestion pills — only shown on empty state */}
      {isEmpty && (
        <div className="flex-shrink-0 px-4 pb-3">
          <div className="max-w-3xl mx-auto">
            <p className="text-xs text-gray-500 mb-2">Try a story topic:</p>
            <div className="flex flex-wrap gap-2">
              {SUGGESTIONS.map(s => (
                <button
                  key={s}
                  onClick={() => sendSuggestion(s)}
                  className="px-3 py-1.5 text-xs rounded-full border border-gray-300 text-gray-600 hover:border-cod-navy hover:text-cod-navy hover:bg-blue-50 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Setup warning */}
      {!dbReady && (
        <div className="flex-shrink-0 mx-4 mb-3">
          <div className="max-w-3xl mx-auto p-3 bg-yellow-50 border border-yellow-300 rounded-lg text-xs text-yellow-800">
            <strong>Database not ready.</strong> Run the scraper then:{' '}
            <code className="bg-yellow-100 px-1 rounded">npm run ingest</code>
          </div>
        </div>
      )}

      {/* Input area */}
      <div className="flex-shrink-0 border-t border-gray-200 bg-white px-4 py-3">
        <form onSubmit={handleSubmit} className="max-w-3xl mx-auto">
          <div className="flex gap-2 items-end">
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={onKeyDown}
              placeholder="Describe your story or topic… (Enter to send, Shift+Enter for new line)"
              rows={1}
              disabled={!dbReady || isLoading}
              className="flex-1 resize-none rounded-xl border border-gray-300 px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-cod-navy focus:border-transparent disabled:opacity-50 disabled:bg-gray-50 leading-relaxed"
              style={{ maxHeight: '8rem', overflowY: 'auto' }}
              onInput={e => {
                const el = e.currentTarget;
                el.style.height = 'auto';
                el.style.height = Math.min(el.scrollHeight, 128) + 'px';
              }}
            />
            <button
              type="submit"
              disabled={!input.trim() || isLoading || !dbReady}
              className="flex-shrink-0 w-10 h-10 rounded-xl bg-cod-navy text-white flex items-center justify-center hover:bg-cod-navy-light transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              title="Send"
            >
              <SendIcon />
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-full text-center py-16 px-4">
      <div className="w-16 h-16 rounded-2xl bg-cod-navy flex items-center justify-center mb-6">
        <svg className="w-8 h-8 text-white" fill="none" stroke="currentColor" strokeWidth={1.5} viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
        </svg>
      </div>
      <h2 className="text-xl font-semibold text-gray-900 mb-2">Find your expert source</h2>
      <p className="text-gray-500 text-sm max-w-sm leading-relaxed">
        Describe your story or topic and I'll find College of DuPage faculty experts who can help.
      </p>
    </div>
  );
}

function SendIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
    </svg>
  );
}

function BookmarkIcon() {
  return (
    <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
      <path d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z" />
    </svg>
  );
}
