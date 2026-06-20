import { chromium } from '/opt/node22/lib/node_modules/playwright/index.mjs';
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

const dir = path.dirname(new URL(import.meta.url).pathname);
const svgs = readdirSync(dir).filter(f => /^(0[7-9]|1[0-2])-.*\.svg$/.test(f)).sort();

const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome' });
const page = await browser.newPage({ deviceScaleFactor: 1 });

for (const f of svgs) {
  const svg = readFileSync(path.join(dir, f), 'utf8');
  const html = `<!doctype html><html><body style="margin:0">${svg.replace('<svg ', '<svg width="256" height="256" ')}</body></html>`;
  await page.setViewportSize({ width: 256, height: 256 });
  await page.setContent(html, { waitUntil: 'networkidle' });
  const el = await page.$('svg');
  await el.screenshot({ path: path.join(dir, f.replace('.svg', '.png')), omitBackground: true });
  console.log('rendered', f);
}

const items = svgs.map(f => ({ svg: readFileSync(path.join(dir, f), 'utf8'), label: f.replace('.svg','').replace(/^\d+-/,'').replace(/-/g,' ') }));
const cell = (it, size) => `
  <div style="display:flex;flex-direction:column;align-items:center;gap:10px">
    <div style="width:${size}px;height:${size}px;border-radius:${size*0.22}px;overflow:hidden;box-shadow:0 8px 24px rgba(0,0,0,.35)">
      ${it.svg.replace('<svg ', `<svg width="${size}" height="${size}" `)}</div>
    <div style="font:600 16px system-ui;color:#222;text-transform:capitalize">${it.label}</div>
  </div>`;
const sheet = `<!doctype html><html><body style="margin:0;background:#f0f1f5;padding:40px">
  <div style="font:800 26px system-ui;color:#111;margin-bottom:6px">Icon concepts — batch 2</div>
  <div style="font:500 15px system-ui;color:#666;margin-bottom:28px">New directions, shown at 180px with rounded-app mask</div>
  <div style="display:grid;grid-template-columns:repeat(3,180px);gap:46px 56px;justify-content:start">
    ${items.map(it => cell(it, 180)).join('')}</div>
  <div style="font:700 18px system-ui;color:#111;margin:46px 0 18px">64px legibility — light vs dark</div>
  <div style="display:flex;gap:24px;background:#fff;padding:20px;border-radius:16px;width:fit-content">
    ${items.map(it=>`<div style="width:64px;height:64px;border-radius:14px;overflow:hidden">${it.svg.replace('<svg ',`<svg width="64" height="64" `)}</div>`).join('')}</div>
  <div style="display:flex;gap:24px;background:#15162a;padding:20px;border-radius:16px;width:fit-content;margin-top:16px">
    ${items.map(it=>`<div style="width:64px;height:64px;border-radius:14px;overflow:hidden">${it.svg.replace('<svg ',`<svg width="64" height="64" `)}</div>`).join('')}</div>
</body></html>`;
await page.setViewportSize({ width: 820, height: 760 });
await page.setContent(sheet, { waitUntil: 'networkidle' });
const body = await page.$('body');
await body.screenshot({ path: path.join(dir, 'contact-sheet-2.png') });
console.log('rendered contact-sheet-2.png');
await browser.close();
