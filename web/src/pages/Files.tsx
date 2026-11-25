import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type FileInfo } from '../api'
import { Character } from '../components/Character'
import { Back } from '../components/Icons'
import { Markdown } from '../components/Markdown'
import { agentAccessory, agentColor, CHECKER_COLOR } from '../state/reducer'

export function Files() {
  const { runId = '', '*': splat = '' } = useParams()
  const [files, setFiles] = useState<FileInfo[]>([])
  const [agents, setAgents] = useState<Record<string, number>>({})
  const [title, setTitle] = useState('')
  const [content, setContent] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    api.files(runId).then(setFiles).catch((e) => setError(e.message))
    fetch(`/api/runs/${runId}`).then((r) => r.json()).then((d) => {
      setTitle(d.title)
      setAgents(Object.fromEntries((d.agents || []).map((a: { name: string; color_index: number }) => [a.name, a.color_index])))
    }).catch(() => {})
  }, [runId])

  const current = splat || files.find((f) => f.path === 'report.md')?.path || files.find((f) => f.path.endsWith('.md'))?.path || files[0]?.path || ''
  const info = files.find((f) => f.path === current)

  useEffect(() => {
    if (!current) return
    setContent(null)
    api.file(runId, current).then((t) => setContent(typeof t === 'string' ? t : JSON.stringify(t, null, 2))).catch((e) => setContent(`Can't show this file: ${e.message}`))
  }, [runId, current])
  useEffect(() => { document.title = `${current || 'Files'} · ChaCha PA` }, [current])

  const face = (agent: string, size: number) => {
    const idx = agents[agent]
    return idx === undefined
      ? <Character color={CHECKER_COLOR} mood="neutral" size={size} animate={false} />
      : <Character color={agentColor(idx)} accessory={agentAccessory(idx)} mood="neutral" size={size} animate={false} />
  }
  const copy = async () => {
    if (content == null) return
    try { await navigator.clipboard.writeText(content); setCopied(true); setTimeout(() => setCopied(false), 1500) } catch { /* blocked */ }
  }

  return (
    <main className="files-page">
      <header className="run-header">
        <Link className="icon-btn" to={`/runs/${runId}`} aria-label="Back to the run"><Back /></Link>
        <h1>Files · {title}</h1>
        <a className="btn btn-sm" href={api.zipUrl(runId)} download>Download all</a>
      </header>
      <nav className="file-tabs" aria-label="Workspace files">
        {files.map((f) => (
          <Link key={f.path} to={`/runs/${runId}/files/${f.path}`} className="chip" aria-current={f.path === current ? 'page' : undefined}>
            {f.path}
          </Link>
        ))}
      </nav>
      <div className="files-body">
        <nav className="file-list" aria-label="Workspace files">
          {files.map((f) => (
            <Link key={f.path} to={`/runs/${runId}/files/${f.path}`} aria-current={f.path === current ? 'page' : undefined}>
              {face(f.agent, 18)}<span>{f.path}</span>
            </Link>
          ))}
          {files.length === 0 && !error && <span className="muted" style={{ padding: 10, fontSize: 13.5 }}>No files yet.</span>}
        </nav>
        <article className="doc-wrap">
          {error && <p className="form-error">{error}</p>}
          {info && (
            <div className="doc-head">
              {face(info.agent, 28)}
              <span className="txt">
                <span className="mono" style={{ fontSize: 14 }}>{info.path}</span>
                <span className="muted" style={{ fontSize: 12.5 }}>
                  {info.agent ? `by ${info.agent}` : 'workspace file'}{info.versions > 1 ? ` · revised ${info.versions - 1} ${info.versions === 2 ? 'time' : 'times'}` : ''} · {(info.size / 1024).toFixed(1)} KB
                </span>
              </span>
              <button className="btn btn-sm" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
              <a className="btn btn-sm" href={api.fileUrl(runId, info.path)} target="_blank" rel="noreferrer">Raw</a>
            </div>
          )}
          {content === null && current && <p className="muted">Loading…</p>}
          {content !== null && (current.endsWith('.md') ? <Markdown source={content} /> : <pre className="code"><code>{content}</code></pre>)}
          {!current && files.length === 0 && <div className="empty"><span>Files appear here as agents write them.</span></div>}
        </article>
      </div>
    </main>
  )
}
