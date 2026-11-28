import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { MemoryRouter } from 'react-router-dom'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import '../styles/tokens.css'
import '../styles/app.css'
import recorded from './run.json'
import type { RunEvent } from '../state/types'
import { scrub } from './clock'
import { Replay } from './Replay'

// MemoryRouter: the app's components use links; on a static page they must never leave it.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <MemoryRouter><Replay events={scrub(recorded as RunEvent[])} /></MemoryRouter>
  </StrictMode>,
)
