import React, { useState } from 'react';
import { Copy, Check } from 'lucide-react';
import { FEEDBACK_NORMAL } from '@/styles/ux-timing';

interface CodeBlockProps {
  code: string;
  startLine?: number;
  maxLines?: number;
  language?: string;
  highlights?: number[];
  linePrefix?: Map<number, '+' | '-'>;
}

export function CodeBlock({
  code,
  startLine = 1,
  maxLines = 20,
  language,
  highlights = [],
  linePrefix,
}: CodeBlockProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const lines = code.split('\n');
  const totalLines = lines.length;
  const displayLines = isExpanded ? lines : lines.slice(0, maxLines);
  const needsExpansion = totalLines > maxLines;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), FEEDBACK_NORMAL);
  };

  const getLineBackground = (lineNumber: number) => {
    if (highlights.includes(lineNumber)) {
      return 'bg-yellow-100 dark:bg-yellow-900/30';
    }
    if (linePrefix) {
      const prefix = linePrefix.get(lineNumber);
      if (prefix === '+') return 'bg-green-50 dark:bg-green-900/20';
      if (prefix === '-') return 'bg-red-50 dark:bg-red-900/20';
    }
    return '';
  };

  return (
    <div className="relative rounded-md border border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900">
      {/* Header with language and copy button */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-gray-200 dark:border-gray-700">
        {language && (
          <span className="text-xs text-gray-500 dark:text-gray-400 font-medium">
            {language}
          </span>
        )}
        <button
          onClick={handleCopy}
          className="ml-auto p-1.5 rounded hover:bg-gray-200 dark:hover:bg-gray-800 transition-colors duration-fast"
          title="Copy code"
        >
          {copied ? (
            <Check className="w-4 h-4 text-green-600" />
          ) : (
            <Copy className="w-4 h-4 text-gray-600 dark:text-gray-400" />
          )}
        </button>
      </div>

      {/* Code content */}
      <div className="relative">
        <div className="overflow-x-auto">
          <div className="grid grid-cols-[auto_1fr] font-mono text-sm">
            {displayLines.map((line, idx) => {
              const lineNumber = startLine + idx;
              const bgClass = getLineBackground(lineNumber);
              const prefix = linePrefix?.get(lineNumber);

              return (
                <React.Fragment key={`line-${lineNumber}-${idx}`}>
                  {/* Line number column */}
                  <div
                    className={`px-4 py-1 text-right text-gray-400 dark:text-gray-600 select-none border-r border-gray-200 dark:border-gray-700 ${bgClass}`}
                  >
                    {lineNumber}
                  </div>
                  {/* Code column */}
                  <div
                    className={`px-4 py-1 ${bgClass}`}
                  >
                    {prefix && (
                      <span
                        className={
                          prefix === '+'
                            ? 'text-green-600 dark:text-green-400'
                            : 'text-red-600 dark:text-red-400'
                        }
                      >
                        {prefix}{' '}
                      </span>
                    )}
                    <span className="text-gray-800 dark:text-gray-200">
                      {line || ' '}
                    </span>
                  </div>
                </React.Fragment>
              );
            })}
          </div>
        </div>

        {/* Fade overlay and expand button */}
        {needsExpansion && !isExpanded && (
          <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-gray-50 dark:from-gray-900 to-transparent pointer-events-none" />
        )}
      </div>

      {needsExpansion && (
        <div className="px-4 py-2 border-t border-gray-200 dark:border-gray-700 text-center">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
          >
            {isExpanded
              ? '收起'
              : `展开全部 (${totalLines} 行)`}
          </button>
        </div>
      )}
    </div>
  );
}
