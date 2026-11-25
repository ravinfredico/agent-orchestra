import { StrictMode, useEffect, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import '@fontsource-variable/geist'
import '@fontsource-variable/geist-mono'
import './styles/tokens.css'
import './styles/app.css'
import { api, AUTH_EVENT } from './api'
import { Character } from './components/Character'
import { Shell } from './components/Shell'
import { Files } from './pages/Files'
import { History } from './pages/History'
import { NewRun } from './pages/NewRun'
import { RunPage } from './pages/RunPage'
import { ORCHESTRATOR_COLOR } from './state/reducer'

function Login({ onDone }: { onDone: () => void }) {
  const [token, setToken] = useState('')
  const [err, setErr] = useState('')
  return (
    <div className="center-page">
      <div className="login">
        <Character color={ORCHESTRATOR_COLOR} accessory="bow" mood="neutral" size={64} />
        <h1 style={{ margin: 0, fontSize: 26 }}>ChaCha PA</h1>
        <form onSubmit={async (e) => {
          e.preventDefault()
          try { await api.login(token); onDone() } catch { setErr('That token is not right.') }
        }}>
          <label className="field"><span>App token</span>
            <input type="password" autoComplete="current-password" value={token} onChange={(e) => setToken(e.target.value)} />
          </label>
          {err && <span className="form-error" role="alert">{err}</span>}
          <button className="btn btn-primary" type="submit" disabled={!token}>Sign in</button>
        </form>
      </div>
    </div>
  )
}

function App() {
  const [needLogin, setNeedLogin] = useState(false)
  useEffect(() => {
    const on = () => setNeedLogin(true)
    window.addEventListener(AUTH_EVENT, on)
    return () => window.removeEventListener(AUTH_EVENT, on)
  }, [])
  if (needLogin) return <Login onDone={() => { setNeedLogin(false); window.location.reload() }} />
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<NewRun />} />
          <Route path="/runs/:runId" element={<RunPage />} />
          <Route path="/history" element={<History />} />
        </Route>
        <Route path="/runs/:runId/files/*" element={<Files />} />
      </Routes>
    </BrowserRouter>
  )
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
