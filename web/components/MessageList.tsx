'use client';

import type { Message } from 'ai';
import SourceCard from './SourceCard';
import type { SourceResult } from '@/lib/faculty';

interface Props {
  messages: Message[];
  isLoading: boolean;
}

export default function MessageList({ messages, isLoading }: Props) {
  return (
    <div className="space-y-6">
      {messages.map(message => (
        <div key={message.id}>
          {message.role === 'user' ? (
            <UserMessage content={message.content} />
          ) : (
            <AssistantMessage message={message} />
          )}
        </div>
      ))}
      {isLoading && <TypingIndicator />}
    </div>
  );
}

function UserMessage({ content }: { content: string }) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[80%] bg-cod-navy text-white rounded-2xl rounded-tr-sm px-4 py-3 text-sm leading-relaxed">
        {content}
      </div>
    </div>
  );
}

function AssistantMessage({ message }: { message: Message }) {
  // Collect tool invocation results (source cards) and text parts
  const toolResults: SourceResult[][] = [];
  const textParts: string[] = [];

  // Handle parts-based message format (AI SDK v4)
  if (message.parts) {
    for (const part of message.parts) {
      if (part.type === 'text' && part.text.trim()) {
        textParts.push(part.text);
      } else if (part.type === 'tool-invocation') {
        const inv = part.toolInvocation;
        if (
          inv.toolName === 'show_sources' &&
          inv.state === 'result' &&
          Array.isArray(inv.result)
        ) {
          toolResults.push(inv.result as SourceResult[]);
        }
      }
    }
  } else {
    // Fallback: toolInvocations + content
    if (message.toolInvocations) {
      for (const inv of message.toolInvocations) {
        if (
          inv.toolName === 'show_sources' &&
          inv.state === 'result' &&
          Array.isArray(inv.result)
        ) {
          toolResults.push(inv.result as SourceResult[]);
        }
      }
    }
    if (message.content?.trim()) {
      textParts.push(message.content);
    }
  }

  const hasContent = toolResults.length > 0 || textParts.some(t => t.trim());
  if (!hasContent) return null;

  return (
    <div className="flex justify-start">
      <div className="max-w-full w-full space-y-4">
        {/* Source cards grid */}
        {toolResults.map((sources, i) =>
          sources.length > 0 ? (
            <div
              key={i}
              className={`grid gap-3 ${
                sources.length === 1 ? 'grid-cols-1 max-w-sm' : 'grid-cols-1 sm:grid-cols-2'
              }`}
            >
              {sources.map(source =>
                source?.id ? <SourceCard key={source.id} source={source} /> : null,
              )}
            </div>
          ) : null,
        )}

        {/* Text response */}
        {textParts.map((text, i) =>
          text.trim() ? (
            <div
              key={i}
              className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3 text-sm leading-relaxed text-gray-800 max-w-prose whitespace-pre-wrap"
            >
              {text}
            </div>
          ) : null,
        )}
      </div>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex justify-start">
      <div className="bg-gray-100 rounded-2xl rounded-tl-sm px-4 py-3">
        <div className="flex gap-1 items-center h-4">
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:0ms]" />
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:150ms]" />
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce [animation-delay:300ms]" />
          <span className="ml-2 text-xs text-gray-500">Finding experts…</span>
        </div>
      </div>
    </div>
  );
}
