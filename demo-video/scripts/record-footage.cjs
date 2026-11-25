// Records demo-mode footage for the Remotion video. Usage: node clips.js <base> <outdir>
const { chromium } = require('playwright');
const [BASE, OUT] = process.argv.slice(2);
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function record(name, { w, h, theme = 'dark' }, fn) {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1,
    recordVideo: { dir: `${OUT}/${name}`, size: { width: w, height: h } } });
  await ctx.addInitScript(t => localStorage.setItem('chacha-theme', t), theme);
  const p = await ctx.newPage();
  const t0 = Date.now();
  await fn(p);
  console.log(name, ((Date.now() - t0) / 1000).toFixed(1) + 's');
  await ctx.close(); await b.close();
}

(async () => {
  // 1. research run: plan, hire, retry, replan, approval, done
  await record('research', { w: 1440, h: 900 }, async (p) => {
    await p.goto(BASE + '/'); await p.waitForSelector('#task'); await sleep(1500);
    await p.click('.suggestions .chip >> text=Research report with sources'); await sleep(1500);
    await p.click('button[aria-label="Start run"]');
    await p.waitForSelector('.approval:not(.resolved)', { timeout: 120000 }); await sleep(3000);
    await p.click('.approval .btn-primary');
    await p.waitForSelector('.outcome', { timeout: 120000 }); await sleep(2500);
  });
  // 2. build run: developer + tester, bug caught, fix routed to developer
  await record('build', { w: 1440, h: 900 }, async (p) => {
    await p.goto(BASE + '/'); await p.waitForSelector('#task'); await sleep(1200);
    await p.click('.suggestions .chip >> text=Small app with passing tests'); await sleep(1200);
    await p.click('button[aria-label="Start run"]');
    await p.waitForSelector('.outcome', { timeout: 120000 }); await sleep(1200);
    await p.locator('.card.replaced .card-head').click(); await sleep(4500);
  });
  // 3. phone, light theme
  await record('phone', { w: 390, h: 844, theme: 'light' }, async (p) => {
    await p.goto(BASE + '/'); await p.waitForSelector('#task'); await sleep(1200);
    await p.click('.suggestions .chip >> text=Research report with sources'); await sleep(1000);
    await p.click('button[aria-label="Start run"]');
    await p.waitForSelector('.approval:not(.resolved)', { timeout: 120000 }); await sleep(2500);
    await p.click('.approval .btn-primary');
    await p.waitForSelector('.outcome', { timeout: 120000 }); await sleep(2500);
  });
  // 4. history and files
  await record('history', { w: 1440, h: 900 }, async (p) => {
    await p.goto(BASE + '/history'); await p.waitForSelector('.run-row'); await sleep(2500);
    await p.locator('.run-row .main-link').last().click(); await p.waitForSelector('.outcome'); await sleep(1000);
    await p.click('.outcome a.btn-primary'); await p.waitForSelector('.doc'); await sleep(3500);
  });
})().catch(e => { console.error(e); process.exit(1); });
