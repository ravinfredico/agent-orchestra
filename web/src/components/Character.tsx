import { useEffect, useMemo, useRef, useState } from 'react'
import type { Mood } from '../state/types'

type Accessory = 'none' | 'bow' | 'antenna' | 'monocle'

interface Props {
  color: string
  mood?: Mood
  accessory?: Accessory | string
  size?: number
  label?: string          // screen reader text; omit to hide the face from assistive tech
  animate?: boolean       // bob, blink, hop on pass, shake on send-back
}

const INK = '#111111'

function hash(s: string) {
  let h = 0
  for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0
  return Math.abs(h)
}

/** Agent character: a rounded body in the agent's color whose face shows its status (DESIGN.md 3.1). */
export function Character({ color, mood = 'neutral', accessory = 'none', size = 36, label, animate = true }: Props) {
  const prev = useRef<Mood>(mood)
  const [react, setReact] = useState<'' | 'hop' | 'shake'>('')
  useEffect(() => {
    if (!animate || prev.current === mood) return
    const kind = mood === 'happy' ? 'hop' : mood === 'sad' ? 'shake' : ''
    prev.current = mood
    if (!kind) return
    setReact(kind)
    const id = window.setTimeout(() => setReact(''), 320)
    return () => window.clearTimeout(id)
  }, [mood, animate])

  const blink = useMemo(() => {
    const h = hash(color + (label || ''))
    return { '--blink': `${4 + (h % 3)}s`, '--blink-delay': `${(h % 17) / 10}s` } as React.CSSProperties
  }, [color, label])

  const cls = ['char', animate ? `m-${mood}` : '', react].filter(Boolean).join(' ')
  const a11y = label ? { role: 'img', 'aria-label': label } : { 'aria-hidden': true as const }

  return (
    <span className={cls} style={{ width: size, height: size, ...(animate ? blink : {}) }} {...a11y}>
      <svg width={size} height={size} viewBox="0 0 40 40" focusable="false">
        <rect x="2" y="4" width="36" height="34" rx="14" fill={color} />
        {accessory === 'bow' && <path d="M14 33 L20 35.5 L14 38 Z M26 33 L20 35.5 L26 38 Z" fill={INK} />}
        {accessory === 'antenna' && (
          <>
            <path d="M20 4 V1" stroke={INK} strokeWidth="2" strokeLinecap="round" />
            <circle cx="20" cy="1.5" r="1.5" fill={INK} />
          </>
        )}
        <Face mood={mood} />
        {accessory === 'monocle' && (
          <>
            <circle cx="26" cy="19.5" r="6.8" fill="none" stroke={INK} strokeWidth="1.6" />
            <path d="M32.5 22 L36 31" stroke={INK} strokeWidth="1.2" />
          </>
        )}
      </svg>
    </span>
  )
}

function Face({ mood }: { mood: Mood }) {
  const line = { stroke: INK, strokeWidth: 2.4, fill: 'none', strokeLinecap: 'round' as const }
  const mouth = { stroke: INK, strokeWidth: 2.2, fill: 'none', strokeLinecap: 'round' as const }
  switch (mood) {
    case 'working':
      return (
        <>
          <g className="eyes">
            <circle cx="14" cy="19" r="5" fill="#fff" /><circle cx="26" cy="19" r="5" fill="#fff" />
            <circle cx="16" cy="20.5" r="2.4" fill={INK} /><circle cx="28" cy="20.5" r="2.4" fill={INK} />
          </g>
          <circle cx="20" cy="29.5" r="1.8" fill={INK} />
        </>
      )
    case 'waiting':
      return (
        <>
          <path d="M10 19.5 H18 M22 19.5 H30" {...line} />
          <path d="M16.5 29 H23.5" {...mouth} />
        </>
      )
    case 'happy':
      return (
        <>
          <path d="M10 21 Q14 15.5 18 21 M22 21 Q26 15.5 30 21" {...line} />
          <path d="M15 27 Q20 32.5 25 27" {...mouth} />
        </>
      )
    case 'sad':
      return (
        <>
          <g className="eyes">
            <circle cx="14" cy="20" r="5" fill="#fff" /><circle cx="26" cy="20" r="5" fill="#fff" />
            <circle cx="14" cy="21.5" r="2.4" fill={INK} /><circle cx="26" cy="21.5" r="2.4" fill={INK} />
          </g>
          <path d="M9.5 12.5 L17 14.5 M30.5 12.5 L23 14.5" {...mouth} />
          <path d="M15.5 31 Q20 27 24.5 31" {...mouth} />
        </>
      )
    case 'sleepy':
      return (
        <>
          <path d="M10 19 Q14 22.5 18 19 M22 19 Q26 22.5 30 19" {...line} />
          <path d="M17.5 29 H22.5" {...mouth} />
        </>
      )
    default:
      return (
        <>
          <g className="eyes">
            <circle cx="14" cy="19" r="5" fill="#fff" /><circle cx="26" cy="19" r="5" fill="#fff" />
            <circle cx="14" cy="19" r="2.4" fill={INK} /><circle cx="26" cy="19" r="2.4" fill={INK} />
          </g>
          <path d="M16.5 29 H23.5" {...mouth} />
        </>
      )
  }
}
