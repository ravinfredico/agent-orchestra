import type { ReactNode } from 'react'

// A small, safe markdown renderer for agent output: headings, paragraphs, lists, tables, code,
// bold, inline code and links. Builds React elements, never raw HTML, so nothing can inject markup.

function inline(text: string, key = 0): ReactNode[] {
  const out: ReactNode[] = []
  const re = /(\*\*[^*]+\*\*|`[^`]+`|https?:\/\/[^\s)]+)/g
  let last = 0
  let m: RegExpExecArray | null
  let i = key
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index))
    const t = m[0]
    if (t.startsWith('**')) out.push(<strong key={i++}>{t.slice(2, -2)}</strong>)
    else if (t.startsWith('`')) out.push(<code key={i++}>{t.slice(1, -1)}</code>)
    else out.push(<a key={i++} href={t} target="_blank" rel="noopener noreferrer">{t}</a>)
    last = m.index + t.length
  }
  if (last < text.length) out.push(text.slice(last))
  return out
}

export function Markdown({ source }: { source: string }) {
  const lines = source.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let i = 0
  let k = 0
  while (i < lines.length) {
    const l = lines[i]
    if (/^```/.test(l)) {
      const code: string[] = []
      i++
      while (i < lines.length && !/^```/.test(lines[i])) code.push(lines[i++])
      i++
      blocks.push(<pre className="code" key={k++}><code>{code.join('\n')}</code></pre>)
      continue
    }
    const h = l.match(/^(#{1,4})\s+(.*)/)
    if (h) {
      const level = Math.min(4, h[1].length + 1)
      const Tag = `h${level}` as 'h2' | 'h3' | 'h4'
      blocks.push(<Tag key={k++}>{inline(h[2])}</Tag>)
      i++
      continue
    }
    if (/^\|/.test(l)) {
      const rows: string[] = []
      while (i < lines.length && /^\|/.test(lines[i])) rows.push(lines[i++])
      const cells = (r: string) => r.replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
      const head = cells(rows[0])
      const body = rows.slice(rows[1] && /^\|?\s*:?-/.test(rows[1]) ? 2 : 1).map(cells)
      blocks.push(
        <div className="table-wrap" key={k++}>
          <table>
            <thead><tr>{head.map((c, j) => <th key={j}>{inline(c)}</th>)}</tr></thead>
            <tbody>{body.map((r, j) => <tr key={j}>{r.map((c, n) => <td key={n}>{inline(c)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      )
      continue
    }
    if (/^\s*[-*]\s+/.test(l)) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*[-*]\s+/, ''))
      blocks.push(<ul key={k++}>{items.map((t, j) => <li key={j}>{inline(t)}</li>)}</ul>)
      continue
    }
    if (/^\s*\d+\.\s+/.test(l)) {
      const items: string[] = []
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*\d+\.\s+/, ''))
      blocks.push(<ol key={k++}>{items.map((t, j) => <li key={j}>{inline(t)}</li>)}</ol>)
      continue
    }
    if (!l.trim() || /^<!--.*-->$/.test(l.trim())) { i++; continue }
    const para: string[] = [l]
    i++
    while (i < lines.length && lines[i].trim() && !/^(#|\||```|\s*[-*]\s|\s*\d+\.\s)/.test(lines[i])) para.push(lines[i++])
    blocks.push(<p key={k++}>{inline(para.join(' '))}</p>)
  }
  return <div className="doc">{blocks}</div>
}
