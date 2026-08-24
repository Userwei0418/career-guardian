import { memo, type ReactNode } from "react";

function safeLinkTarget(value: string): { href: string; external: boolean } | null {
  const href = value.trim();
  if (/^\/(?!\/)/.test(href)) return { href, external: false };
  try {
    const url = new URL(href);
    if (url.protocol === "http:" || url.protocol === "https:") return { href: url.toString(), external: true };
  } catch {
    return null;
  }
  return null;
}

function inlineMarkdown(value: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const token = /(`[^`]+`|\*\*[^*]+\*\*|~~[^~]+~~|\[[^\]]+\]\([^)]+\))/g;
  let cursor = 0;
  let match: RegExpExecArray | null;
  while ((match = token.exec(value)) !== null) {
    if (match.index > cursor) nodes.push(value.slice(cursor, match.index));
    const raw = match[0];
    const key = `${keyPrefix}-${match.index}`;
    if (raw.startsWith("`")) {
      nodes.push(<code key={key} className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[0.9em] text-slate-800">{raw.slice(1, -1)}</code>);
    } else if (raw.startsWith("**")) {
      nodes.push(<strong key={key} className="font-semibold text-slate-950">{raw.slice(2, -2)}</strong>);
    } else if (raw.startsWith("~~")) {
      nodes.push(<del key={key}>{raw.slice(2, -2)}</del>);
    } else {
      const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(raw);
      const target = link ? safeLinkTarget(link[2]) : null;
      if (!link || !target) nodes.push(link?.[1] || raw);
      else nodes.push(<a key={key} href={target.href} target={target.external ? "_blank" : undefined} rel={target.external ? "noopener noreferrer" : undefined} className="font-medium text-sky-700 underline decoration-sky-300 underline-offset-2 hover:text-sky-900">{link[1]}</a>);
    }
    cursor = match.index + raw.length;
  }
  if (cursor < value.length) nodes.push(value.slice(cursor));
  return nodes;
}

function tableCells(line: string): string[] {
  return line.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
}

function isTableSeparator(line: string): boolean {
  const cells = tableCells(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell));
}

function isBlockStart(lines: string[], index: number): boolean {
  const line = lines[index] || "";
  return /^\s*```/.test(line)
    || /^#{1,4}\s+/.test(line)
    || /^\s*>\s?/.test(line)
    || /^\s*[-*+]\s+/.test(line)
    || /^\s*\d+[.)]\s+/.test(line)
    || /^\s*(---+|___+|\*\*\*+)\s*$/.test(line)
    || Boolean(lines[index + 1] && line.includes("|") && isTableSeparator(lines[index + 1]));
}

function SafeMarkdown({ content, className = "" }: { content: string; className?: string }) {
  const lines = content.replace(/\r\n?/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }

    const fence = /^\s*```([^`]*)$/.exec(line);
    if (fence) {
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !/^\s*```\s*$/.test(lines[index])) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      blocks.push(<div key={`code-${index}`} className="my-4 overflow-hidden rounded-xl border border-slate-200 bg-slate-950"><div className="border-b border-white/10 px-4 py-2 text-[10px] uppercase tracking-wider text-slate-400">{fence[1].trim() || "text"}</div><pre className="overflow-x-auto p-4 text-xs leading-6 text-slate-100"><code>{code.join("\n")}</code></pre></div>);
      continue;
    }

    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      const level = heading[1].length;
      const headingClass = level === 1 ? "mt-5 text-xl" : level === 2 ? "mt-5 text-lg" : "mt-4 text-base";
      blocks.push(<div key={`heading-${index}`} role="heading" aria-level={level} className={`${headingClass} mb-2 font-semibold text-slate-950`}>{inlineMarkdown(heading[2], `heading-${index}`)}</div>);
      index += 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const quotes: string[] = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quotes.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }
      blocks.push(<blockquote key={`quote-${index}`} className="my-3 border-l-4 border-sky-300 bg-white/70 px-4 py-3 text-sm leading-7 text-slate-700">{quotes.map((item, quoteIndex) => <p key={quoteIndex}>{inlineMarkdown(item, `quote-${index}-${quoteIndex}`)}</p>)}</blockquote>);
      continue;
    }

    const unordered = /^\s*[-*+]\s+(.+)$/.test(line);
    const ordered = /^\s*\d+[.)]\s+(.+)$/.test(line);
    if (unordered || ordered) {
      const items: string[] = [];
      const itemPattern = unordered ? /^\s*[-*+]\s+(.+)$/ : /^\s*\d+[.)]\s+(.+)$/;
      while (index < lines.length) {
        const item = itemPattern.exec(lines[index]);
        if (!item) break;
        items.push(item[1]);
        index += 1;
      }
      const listItems = items.map((item, itemIndex) => <li key={itemIndex} className="pl-1">{inlineMarkdown(item, `list-${index}-${itemIndex}`)}</li>);
      blocks.push(unordered
        ? <ul key={`list-${index}`} className="my-3 list-disc space-y-1.5 pl-5 text-sm leading-7 text-slate-700">{listItems}</ul>
        : <ol key={`list-${index}`} className="my-3 list-decimal space-y-1.5 pl-5 text-sm leading-7 text-slate-700">{listItems}</ol>);
      continue;
    }

    if (line.includes("|") && lines[index + 1] && isTableSeparator(lines[index + 1])) {
      const header = tableCells(line);
      index += 2;
      const rows: string[][] = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) {
        rows.push(tableCells(lines[index]));
        index += 1;
      }
      blocks.push(<div key={`table-${index}`} className="my-4 overflow-x-auto rounded-xl border border-sky-100 bg-white"><table className="w-full min-w-[420px] border-collapse text-left text-xs"><thead className="bg-sky-50"><tr>{header.map((cell, cellIndex) => <th key={cellIndex} className="border-b border-sky-100 px-3 py-2.5 font-semibold text-slate-800">{inlineMarkdown(cell, `th-${index}-${cellIndex}`)}</th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex} className="border-b border-slate-100 last:border-0">{header.map((_, cellIndex) => <td key={cellIndex} className="px-3 py-2.5 align-top text-slate-700">{inlineMarkdown(row[cellIndex] || "", `td-${index}-${rowIndex}-${cellIndex}`)}</td>)}</tr>)}</tbody></table></div>);
      continue;
    }

    if (/^\s*(---+|___+|\*\*\*+)\s*$/.test(line)) {
      blocks.push(<hr key={`rule-${index}`} className="my-4 border-sky-100" />);
      index += 1;
      continue;
    }

    const paragraph: string[] = [line.trim()];
    index += 1;
    while (index < lines.length && lines[index].trim() && !isBlockStart(lines, index)) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push(<p key={`paragraph-${index}`} className="my-2 break-words text-sm leading-7 text-slate-800">{inlineMarkdown(paragraph.join(" "), `paragraph-${index}`)}</p>);
  }

  return <div className={className}>{blocks}</div>;
}

export default memo(SafeMarkdown);
