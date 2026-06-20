import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

const dir = path.dirname(new URL(import.meta.url).pathname);
const all = readdirSync(dir).filter(f => f.endsWith('.svg')).sort();
const sb = all.filter(f => f.startsWith('02'));
const oa = all.filter(f => f.startsWith('03'));

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const page = await browser.newPage({ deviceScaleFactor: 1 });

for (const f of all) {
  const svg = readFileSync(path.join(dir, f), 'utf8');
  await page.setViewportSize({ width: 256, height: 256 });
  await page.setContent(`<!doctype html><html><body style="margin:0">${svg.replace('<svg ', '<svg width="256" height="256" ')}</body></html>`, { waitUntil: 'networkidle' });
  await (await page.$('svg')).screenshot({ path: path.join(dir, f.replace('.svg', '.png')), omitBackground: true });
  console.log('rendered', f);
}

const load = f => ({ svg: readFileSync(path.join(dir, f), 'utf8'), label: f.replace('.svg','').replace(/^\d+\w?-/,'').replace(/-/g,' ') });
const cell = (it, size) => `
  <div style="display:flex;flex-direction:column;align-items:center;gap:10px">
    <div style="width:${size}px;height:${size}px;border-radius:${size*0.22}px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.35)">
      ${it.svg.replace('<svg ', `<svg width="${size}" height="${size}" `)}</div>
    <div style="font:600 15px system-ui;color:#222;text-transform:capitalize">${it.label}</div>
  </div>`;
const row = (title, files) => `
  <div style="font:800 22px system-ui;color:#111;margin:30px 0 4px">${title}</div>
  <div style="display:grid;grid-template-columns:repeat(4,170px);gap:32px 40px;justify-content:start;margin-bottom:10px">
    ${files.map(load).map(it=>cell(it,170)).join('')}</div>
  <div style="display:flex;gap:20px;background:#15162a;padding:16px;border-radius:14px;width:fit-content">
    ${files.map(load).map(it=>`<div style="width:60px;height:60px;border-radius:13px;overflow:hidden">${it.svg.replace('<svg ',`<svg width="60" height="60" `)}</div>`).join('')}</div>`;

const sheet = `<!doctype html><html><body style="margin:0;background:#f0f1f5;padding:40px">
  <div style="font:800 26px system-ui;color:#111;margin-bottom:18px">Variations — Scoreboard &amp; On Air</div>
  ${row('Scoreboard variations', sb)}
  ${row('On Air variations', oa)}
</body></html>`;
await page.setViewportSize({ width: 900, height: 1000 });
await page.setContent(sheet, { waitUntil: 'networkidle' });
await (await page.$('body')).screenshot({ path: path.join(dir, 'contact-sheet-variations.png') });
console.log('rendered contact-sheet-variations.png');
await browser.close();
