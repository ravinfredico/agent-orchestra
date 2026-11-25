// ChaCha PA home-screen widget for iPhone, using the free Scriptable app.
// Shows the running task (or the last result), the team size, time and usage. Tap to open the run.
//
// Setup (once):
//   1. Install Scriptable from the App Store. Create a new script, paste this file, name it "ChaCha PA".
//   2. Fill in CONFIG below. The phone must reach your server: your Cloudflare Tunnel URL when hosted,
//      or the laptop's LAN address if you start the server with --host 0.0.0.0 and APP_TOKEN set.
//   3. Long-press the home screen > + > Scriptable > pick a size (small or medium) > Add.
//      Long-press the widget > Edit Widget > Script: "ChaCha PA".
//   iOS decides how often widgets refresh, usually every 5 to 15 minutes.
//
// Secrets: instead of typing them below, you can store them once in Scriptable's Keychain
// (run `Keychain.set("chacha_app_token", "…")` in a scratch script). Keychain values win.

const CONFIG = {
  url: "https://pa.example.com",   // where ChaCha PA is reachable from the phone, no trailing slash
  appToken: "",                    // APP_TOKEN from your .env
  accessClientId: "",              // Cloudflare Access service token (only when hosted behind Access)
  accessClientSecret: "",
}

const STATUS_LABEL = {
  created: "Starting", running: "Running", finished: "Finished", gave_up: "Out of budget",
  failed: "Crashed", stopped: "Stopped", interrupted: "Interrupted",
}
const STATUS_DOT = {
  created: "text", running: "text", finished: "pass", gave_up: "check", failed: "fail", stopped: "muted", interrupted: "muted",
}

function clock(s) {
  s = Math.max(0, Math.round(s || 0))
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60
  const pad = (n) => String(n).padStart(2, "0")
  return h ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`
}

function ago(epochSeconds, nowMs) {
  const s = Math.max(0, Math.round(nowMs / 1000 - epochSeconds))
  if (s < 60) return "just now"
  if (s < 3600) return `${Math.floor(s / 60)} min ago`
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`
  return `${Math.floor(s / 86400)} d ago`
}

/** Turn GET /api/status (or an error) into what the widget shows. Pure, so it can be tested off the phone. */
function describe(status, error, base, nowMs) {
  if (error) return { label: "ChaCha PA", title: "Can't reach ChaCha PA", detail: String(error).slice(0, 80), dot: "fail", url: base }
  const running = (status && status.running) || []
  if (running.length) {
    const r = running.find((x) => x.needs_approval) || running[0]
    const team = `${r.agents} ${r.agents === 1 ? "agent" : "agents"}`
    return {
      label: r.needs_approval ? "Needs your approval" : "Running",
      title: r.title,
      detail: `${team} · ${clock(r.elapsed_s)} · $${Number(r.cost_usd || 0).toFixed(2)} est.`,
      more: running.length > 1 ? `+${running.length - 1} more running` : "",
      dot: r.needs_approval ? "check" : "text",
      live: true,
      url: `${base}/runs/${r.id}`,
    }
  }
  const last = status && status.last
  if (last) {
    return {
      label: STATUS_LABEL[last.status] || last.status,
      title: last.title,
      detail: last.ended_at ? ago(last.ended_at, nowMs) : "",
      dot: STATUS_DOT[last.status] || "muted",
      url: `${base}/runs/${last.id}`,
    }
  }
  return { label: "ChaCha PA", title: "No runs yet", detail: "Start one from the app", dot: "muted", url: base }
}

// ---- Scriptable only below ---------------------------------------------------------------

function secret(key, fallback) {
  try { if (Keychain.contains(key)) return Keychain.get(key) } catch (e) { /* no keychain entry */ }
  return fallback
}

async function fetchStatus(base) {
  const req = new Request(`${base}/api/status`)
  req.timeoutInterval = 10
  req.headers = {}
  const token = secret("chacha_app_token", CONFIG.appToken)
  const cfId = secret("chacha_cf_id", CONFIG.accessClientId)
  const cfSecret = secret("chacha_cf_secret", CONFIG.accessClientSecret)
  if (token) req.headers["Authorization"] = `Bearer ${token}`
  if (cfId && cfSecret) {
    req.headers["CF-Access-Client-Id"] = cfId
    req.headers["CF-Access-Client-Secret"] = cfSecret
  }
  const data = await req.loadJSON()
  const code = req.response && req.response.statusCode
  if (code === 401) throw new Error("Sign-in failed: check appToken")
  if (code && code >= 400) throw new Error(`Server answered ${code}`)
  return data
}

function render(model, family) {
  const dyn = (light, dark) => Color.dynamic(new Color(light), new Color(dark))
  const C = {
    bg: dyn("#FFFFFF", "#0A0A0A"), text: dyn("#0A0A0A", "#F5F5F5"), text2: dyn("#5C5C5C", "#A3A3A3"),
    pass: dyn("#15803D", "#4ADE80"), fail: dyn("#B91C1C", "#F87171"), check: dyn("#A16207", "#FBBF24"),
  }
  const dotColor = { pass: C.pass, fail: C.fail, check: C.check, text: C.text, muted: C.text2 }[model.dot] || C.text2
  const small = family === "small"

  const w = new ListWidget()
  w.backgroundColor = C.bg
  w.url = model.url
  w.setPadding(14, 14, 14, 14)
  if (model.live) w.refreshAfterDate = new Date(Date.now() + 5 * 60 * 1000)

  const top = w.addStack()
  top.centerAlignContent()
  const dot = top.addText("●")
  dot.font = Font.systemFont(9)
  dot.textColor = dotColor
  top.addSpacer(5)
  const label = top.addText(model.label)
  label.font = Font.mediumSystemFont(12)
  label.textColor = model.dot === "check" ? C.check : C.text2
  label.lineLimit = 1

  w.addSpacer(6)
  const title = w.addText(model.title || "")
  title.font = Font.semiboldSystemFont(small ? 14 : 16)
  title.textColor = C.text
  title.lineLimit = small ? 3 : 2
  title.minimumScaleFactor = 0.8

  w.addSpacer()
  if (model.detail) {
    const d = w.addText(model.detail)
    d.font = Font.regularMonospacedSystemFont(11)
    d.textColor = C.text2
    d.lineLimit = 1
    d.minimumScaleFactor = 0.7
  }
  if (model.more && !small) {
    const m = w.addText(model.more)
    m.font = Font.systemFont(11)
    m.textColor = C.text2
  }
  return w
}

async function main() {
  const base = CONFIG.url.replace(/\/+$/, "")
  let status = null, error = null
  try { status = await fetchStatus(base) } catch (e) { error = e.message || e }
  const widget = render(describe(status, error, base, Date.now()), config.widgetFamily || "medium")
  if (config.runsInWidget) Script.setWidget(widget)
  else await widget.presentMedium()
  Script.complete()
}

if (typeof ListWidget !== "undefined") {
  await main()
} else if (typeof module !== "undefined") {
  module.exports = { describe, clock, ago }   // tests (web/src/test/widget.test.ts)
}
