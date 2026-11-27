// Accessibility audit (IMPLEMENTATION.md 4.6, DESIGN.md section 8).
// Needs the demo server running:  python -m server --fake   (then: cd web && npm run a11y)
// First time only: npx playwright install chromium
//
// For every screen, in both themes, at 1440 and 390 px:
//   1. axe-core (WCAG 2.2 AA + best practice) must find nothing
//   2. every Tab stop must be on screen and show a focus ring
// Plus: the Stop dialog keeps focus inside and returns it to Stop.
// Exits 1 on any problem.
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://127.0.0.1:8000'
const AXE = readFileSync(createRequire(import.meta.url).resolve('axe-core/axe.min.js'), 'utf8')
const problems = []
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const startRun = (task) => fetch(`${BASE}/api/runs`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task, options: {} }),
}).then((r) => r.json()).then((r) => r.id)

async function axe(page, screen) {
  await sleep(350)   // let enter animations (opacity) finish, or axe measures half-faded colors
  await page.addScriptTag({ content: AXE })
  const res = await page.evaluate(() => window.axe.run(document, {
    runOnly: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'],
  }))
  for (const v of res.violations) for (const n of v.nodes) problems.push(`${screen}: axe ${v.id} (${v.impact}) at ${n.target.join(' ')}`)
}

async function tabWalk(page, screen) {
  await page.evaluate(() => { document.activeElement?.blur(); window.scrollTo(0, 0) })
  let first = null
  for (let i = 0; i < 80; i++) {
    await page.keyboard.press('Tab')
    const f = await page.evaluate(() => {
      const el = document.activeElement
      if (!el || el === document.body) return null
      const ring = (n) => { const c = getComputedStyle(n); return c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) > 0 }
      let shown = ring(el)
      for (let p = el.parentElement, d = 0; p && d < 3 && !shown; p = p.parentElement, d++) shown = ring(p)
      if (!shown && el.nextElementSibling) shown = ring(el.nextElementSibling)   // custom switch after a hidden checkbox
      const r = el.getBoundingClientRect()
      const onScreen = r.width > 0 && r.right > 0 && r.left < innerWidth && getComputedStyle(el).visibility !== 'hidden'
      const name = (el.getAttribute('aria-label') || el.textContent || el.getAttribute('placeholder') || el.tagName).trim().slice(0, 40)
      return { key: `${el.tagName}|${name}|${Math.round(r.left)}|${Math.round(r.top + scrollY)}`, name, shown, onScreen }
    })
    if (!f) continue
    if (f.key === first) break
    first ??= f.key
    if (!f.onScreen) problems.push(`${screen}: Tab reaches "${f.name}", which is off screen`)
    if (!f.shown) problems.push(`${screen}: "${f.name}" has no visible focus ring`)
  }
}

async function check(page, screen) { await axe(page, screen); await tabWalk(page, screen) }

const browser = await chromium.launch()
for (const theme of ['dark', 'light']) for (const [w, h] of [[1440, 900], [390, 844]]) {
  const tag = `${theme} ${w}px`
  const ctx = await browser.newContext({ viewport: { width: w, height: h } })
  await ctx.addInitScript((t) => localStorage.setItem('chacha-theme', t), theme)
  const page = await ctx.newPage()

  await page.goto(`${BASE}/`); await page.waitForSelector('#task')
  await page.click('button[aria-controls="run-options"]')
  await check(page, `${tag} new run`)

  const id = await startRun('Accessibility audit run')
  await page.goto(`${BASE}/runs/${id}`); await page.waitForSelector('.approval:not(.resolved)', { timeout: 90000 })
  await check(page, `${tag} live run with approval`)
  await page.click('.approval .btn-primary'); await page.waitForSelector('.outcome', { timeout: 90000 })
  await page.locator('.card-head').first().click()
  await check(page, `${tag} finished run`)

  await page.goto(`${BASE}/runs/${id}/files`); await page.waitForSelector('.doc, .code')
  await check(page, `${tag} files`)

  await page.goto(`${BASE}/history`); await page.waitForSelector('.run-row')
  await page.locator('.run-row .icon-btn').first().click()
  await axe(page, `${tag} history menu`)
  await page.keyboard.press('Escape')
  await check(page, `${tag} history`)

  const id2 = await startRun('Accessibility audit stop')
  await page.goto(`${BASE}/runs/${id2}`); await page.waitForSelector('.btn-stop')
  await page.focus('.btn-stop'); await page.keyboard.press('Enter'); await page.waitForSelector('[role=dialog]')
  await axe(page, `${tag} stop dialog`)
  for (let i = 0; i < 4; i++) {
    await page.keyboard.press('Tab')
    if (!(await page.evaluate(() => !!document.activeElement?.closest('[role=dialog]')))) problems.push(`${tag} stop dialog: Tab left the dialog`)
  }
  await page.keyboard.press('Escape')
  if (!(await page.evaluate(() => document.activeElement?.classList.contains('btn-stop')))) problems.push(`${tag} stop dialog: focus did not return to Stop`)
  await page.click('.btn-stop'); await page.click('[role=dialog] .btn-danger'); await page.waitForSelector('.outcome', { timeout: 30000 })
  await check(page, `${tag} stopped run`)

  const team = await (await fetch(`${BASE}/api/teams`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: `A11y team ${theme} ${w}`, goal: 'Audit', members: [{ name: 'scout', role: 'Finds things', tools: ['web'], tier: 'haiku' }],
      schedule: [{ cron: '0 9 * * 1-5', task: 'Brief' }] }) })).json()
  await page.goto(`${BASE}/teams/${team.id}`); await page.waitForSelector('#room-msg')
  await check(page, `${tag} team room`)
  await page.goto(`${BASE}/teams/${team.id}/edit`); await page.waitForSelector('.team-form')
  await check(page, `${tag} team editor`)
  await page.goto(`${BASE}/teams/new`); await page.waitForSelector('#team-goal')
  await check(page, `${tag} team builder`)
  await page.getByRole('button', { name: 'Marketing team' }).click(); await page.waitForSelector('.builder-actions')
  await page.waitForTimeout(400)
  await check(page, `${tag} team proposal`)
  await ctx.close()
}
await browser.close()

const unique = [...new Set(problems)]
console.log(unique.length ? unique.join('\n') : 'No accessibility problems found.')
process.exit(unique.length ? 1 : 0)
