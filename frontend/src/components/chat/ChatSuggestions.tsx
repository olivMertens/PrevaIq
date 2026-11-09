'use client';

export default function ChatSuggestions({
  suggestions, onSelect, compact = false,
}: {suggestions: string[]; onSelect: (suggestion: string) => void; compact?: boolean}) {
  return (
    <div className={`grid min-w-0 gap-1.5 sm:grid-cols-2 ${compact ? 'mb-2' : 'mt-2'}`}>
      {suggestions.slice(0, compact ? 4 : 3).map((suggestion, index) => (
        <button key={index} type="button" onClick={() => onSelect(suggestion)} title={suggestion}
          className="min-w-0 truncate rounded-lg border border-indigo-100 bg-indigo-50 px-2.5 py-2 text-left text-xs text-indigo-800 transition-colors hover:bg-indigo-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600">
          {suggestion}
        </button>
      ))}
    </div>
  );
}
