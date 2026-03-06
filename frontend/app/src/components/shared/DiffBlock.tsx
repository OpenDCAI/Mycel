import { useMemo } from 'react';
import { diffLines } from 'diff';
import type { Change } from 'diff';
import { CodeBlock } from './CodeBlock';

interface DiffBlockProps {
  oldText: string;
  newText: string;
  fileName?: string;
  maxLines?: number;
}

export function DiffBlock({
  oldText,
  newText,
  fileName,
  maxLines = 20,
}: DiffBlockProps) {
  const { unifiedDiff, linePrefix } = useMemo(() => {
    const changes = diffLines(oldText, newText);
    const lines: string[] = [];
    const prefixMap = new Map<number, '+' | '-'>();
    let lineNumber = 1;

    changes.forEach((change: Change) => {
      const changeLines = change.value.split('\n');
      // Remove last empty line if exists
      if (changeLines[changeLines.length - 1] === '') {
        changeLines.pop();
      }

      changeLines.forEach((line) => {
        if (change.added) {
          prefixMap.set(lineNumber, '+');
          lines.push(line);
          lineNumber++;
        } else if (change.removed) {
          prefixMap.set(lineNumber, '-');
          lines.push(line);
          lineNumber++;
        } else {
          lines.push(line);
          lineNumber++;
        }
      });
    });

    return {
      unifiedDiff: lines.join('\n'),
      linePrefix: prefixMap,
    };
  }, [oldText, newText]);

  return (
    <div className="space-y-2">
      {fileName && (
        <div className="text-sm font-medium text-gray-700 dark:text-gray-300 px-1">
          {fileName}
        </div>
      )}
      <CodeBlock
        code={unifiedDiff}
        startLine={1}
        maxLines={maxLines}
        language="diff"
        linePrefix={linePrefix}
      />
    </div>
  );
}
