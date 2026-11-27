// Accessibility check for the static replay page (M6).
// Build and serve it first:  npm run build:replay && python -m http.server 8123 -d ../replay/dist
// Then:  npm run a11y:replay   (or pass another URL)
// axe-core (WCAG 2.2 AA + best practice), both themes, 1440 and 390 px, mid-run and at the end.
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { chromium } from 'playwright'

const URL = process.argv[2] || 'http://127.0.0.1:8123/'
const AXE = readFileSync(createRequire(import.meta.url).resolve('axe-core/axe.min.js'), 'utf8')
const problems = []
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function axe(page, screen) {
  await sleep(400)
  await page.addScriptTag({ content: AXE })
  const res = await page.evaluate(() => window.axe.run(document, {
    runOnly: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice'],
  }))
  for (const v of res.violations) for (const n of v.nodes) problems.push(`${screen}: axe ${v.id} (${v.impact}) at ${n.target.join(' ')}`)
}

const browser = await chromium.launch()
for (const scheme of ['dark', 'light']) for (const [w, h] of [[1440, 900], [390, 844]]) {
  const tag = `${scheme} ${w}px`
  const ctx = await browser.newContext({ viewport: { width: w, height: h }, colorScheme: scheme })
  const page = await ctx.newPage()
  await page.goto(URL)
  await page.getByRole('button', { name: 'Pause' }).click()
  await page.getByLabel('Position').fill('40')
  await axe(page, `${tag} replay mid-run`)
  await page.getByLabel('Position').fill(await page.getByLabel('Position').getAttribute('max'))
  await page.waitForSelector('text=Replay finished')
  await axe(page, `${tag} replay finished`)
  await ctx.close()
}
await browser.close()
if (problems.length) { console.log(problems.join('\n')); process.exit(1) }
console.log('No accessibility problems found on the replay page.')
