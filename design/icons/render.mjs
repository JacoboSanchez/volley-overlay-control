import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

const dir = path.dirname(new URL(import.meta.url).pathname);
const svgs = readdirSync(dir).filter(f => f.endsWith('.svg')).sort();

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const page = await browser.newPage({ deviceScaleFactor: 1 });

// Render each SVG to a 256x256 PNG
for (const f of svgs) {
  const svg = readFileSync(path.join(dir, f), 'utf8');
  const html = `<!doctype html><html><body style="margin:0;padding:0">${svg.replace('<svg ', '<svg width="256" height="256" ')}</body></html>`;
  await page.setContent(html, { waitUntil: 'networkidle' });
  await page.setViewportSize({ width: 256, height: 256 });
  const el = await page.$('svg');
  await el.screenshot({ path: path.join(dir, f.replace('.svg', '.png')), omitBackground: true });
  console.log('rendered', f);
}

// Contact sheet: all designs side by side with labels, on both light + dark + rounded mask preview
const items = svgs.map(f => {
  const svg = readFileSync(path.join(dir, f), 'utf8');
  const label = f.replace('.svg','').replace(/^\d+-/,'').replace(/-/g,' ');
  return { svg, label };
});

const cell = (it, size) => `
  <div style="display:flex;flex-direction:column;align-items:center;gap:10px">
    <div style="width:${size}px;height:${size}px;border-radius:${size*0.22}px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.35)">
      ${it.svg.replace('<svg ', `<svg width="${size}" height="${size}" `)}
    </div>
    <div style="font:600 16px system-ui;color:#222;text-align:center;text-transform:capitalize">${it.label}</div>
  </div>`;

const sheet = `<!doctype html><html><body style="margin:0;background:#f0f1f5;padding:40px">
  <div style="font:800 26px system-ui;color:#111;margin-bottom:6px">Volley Overlay Control — icon concepts</div>
  <div style="font:500 15px system-ui;color:#666;margin-bottom:28px">Each shown at 180px with a rounded-app mask</div>
  <div style="display:grid;grid-template-columns:repeat(3,180px);gap:46px 56px;justify-content:start">
    ${items.map(it => cell(it, 180)).join('')}
  </div>
  <div style="font:700 18px system-ui;color:#111;margin:46px 0 18px">Small-size legibility (64px) — light vs dark</div>
  <div style="display:flex;gap:24px;flex-wrap:wrap;background:#ffffff;padding:20px;border-radius:16px;width:fit-content">
    ${items.map(it=>`<div style="width:64px;height:64px;border-radius:14px;overflow:hidden">${it.svg.replace('<svg ',`<svg width="64" height="64" `)}</div>`).join('')}
  </div>
  <div style="display:flex;gap:24px;flex-wrap:wrap;background:#15162a;padding:20px;border-radius:16px;width:fit-content;margin-top:16px">
    ${items.map(it=>`<div style="width:64px;height:64px;border-radius:14px;overflow:hidden">${it.svg.replace('<svg ',`<svg width="64" height="64" `)}</div>`).join('')}
  </div>
</body></html>`;

await page.setViewportSize({ width: 820, height: 1400 });
await page.setContent(sheet, { waitUntil: 'networkidle' });
const body = await page.$('body');
await body.screenshot({ path: path.join(dir, 'contact-sheet.png') });
console.log('rendered contact-sheet.png');

await browser.close();
