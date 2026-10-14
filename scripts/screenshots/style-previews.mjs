// Generate small, deterministic thumbnails from the real overlay renderers.
// Called by run.sh before the operator-facing screenshots are captured.
import { chromium } from 'playwright';
import { readdir, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const root = fileURLToPath(new URL('../../', import.meta.url));
const base = process.env.SCREENSHOT_BASE_URL || 'http://localhost:8181';
const python = process.env.SCREENSHOT_PYTHON || resolve(root, '.venv/bin/python');
const output = resolve(root, 'overlay_static/img/style-previews');
const styles = (await readdir(resolve(root, 'overlay_templates')))
  .filter((name) => name.endsWith('.html') && !name.startsWith('_') && !['base.html', 'mosaic.html'].includes(name))
  .map((name) => name === 'index.html' ? 'default' : name.slice(0, -5)).sort();
const summaries = ['brand_ledger', 'bento', 'glass', 'brand_columns', 'ledger_diff', 'bumper'];
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  args: ['--no-sandbox', '--disable-dev-shm-usage'],
  ...(process.env.SCREENSHOT_CHROMIUM_PATH ? { executablePath: process.env.SCREENSHOT_CHROMIUM_PATH } : {}),
});
try {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  // External font hosts are optional to render the preview. Keep captures offline.
  await page.route(/^https:\/\//, (route) => route.abort());
  const failures = [];
  page.on('pageerror', (error) => failures.push(error.message));
  page.on('websocket', () => failures.push('A style example opened a live WebSocket'));
  for (const [kind, ids] of [['overlay', styles], ['summary', summaries]]) {
    for (const id of ids) {
      const url = kind === 'overlay' ? `/overlay-preview/${id}` : `/overlay-preview/default?summary=${id}`;
      const response = await page.goto(`${base}${url}`, { waitUntil: 'networkidle' });
      if (!response?.ok()) throw new Error(`Preview failed: ${url}`);
      await page.waitForFunction(() => document.getElementById('home-points')?.textContent === '25');
      await page.waitForTimeout(1100);
      const clip = kind === 'summary' ? undefined : await page.evaluate(() => {
        const rect = document.getElementById('scoreboard-container').getBoundingClientRect();
        const x = Math.max(0, Math.floor(rect.x - 12));
        const y = Math.max(0, Math.floor(rect.y - 12));
        return { x, y, width: Math.min(1920 - x, Math.ceil(rect.width + 24)), height: Math.min(1080 - y, Math.ceil(rect.height + 24)) };
      });
      const png = await page.screenshot({ omitBackground: true, ...(clip ? { clip } : {}) });
      const result = spawnSync(python, ['-c',
        'import sys,io; from PIL import Image,ImageOps; im=Image.open(io.BytesIO(sys.stdin.buffer.read())).convert("RGBA"); bg=Image.new("RGBA",im.size,"#243346"); bg.alpha_composite(im); ImageOps.pad(bg.convert("RGB"),(480,270),color="#243346").save(sys.argv[1],"WEBP",quality=82)',
        resolve(output, `${kind}-${id}.webp`)], { input: png });
      if (result.status !== 0) throw new Error(result.stderr.toString());
    }
  }
  if (failures.length) throw new Error(`Renderer errors: ${failures.join('; ')}`);
  console.log(`Generated ${styles.length + summaries.length} style thumbnails.`);
} finally {
  await browser.close();
}
