import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { spawnSync } from 'node:child_process';

const required = ['public/index.html', 'public/styles.css', 'public/app.js', 'public/favicon.svg'];
for (const path of required) {
  assert.ok(existsSync(resolve(path)), 'Missing deployment asset: ' + path);
}
const html = readFileSync(resolve('public/index.html'), 'utf8');
const styles = readFileSync(resolve('public/styles.css'), 'utf8');
const config = JSON.parse(readFileSync(resolve('vercel.json'), 'utf8'));
assert.match(html, /<title>SiteGuard QR/);
assert.match(html, /href="\/styles\.css"/);
assert.match(html, /src="\/app\.js"/);
assert.match(html, /data-view="overview"/);
assert.match(html, /data-view="kiosk"/);
assert.match(html, /data-view="reviews"/);
assert.match(html, /data-view="exports"/);
assert.match(html, /No live attendance data/);
assert.ok(styles.length > 100, 'Stylesheet should not be empty');
assert.equal(config.framework, null);
assert.equal(config.outputDirectory, 'public');
const parsed = spawnSync(process.execPath, ['--check', resolve('public/app.js')], { encoding: 'utf8' });
assert.equal(parsed.status, 0, parsed.stderr || 'App JavaScript syntax check failed');
console.log('SiteGuard QR static preview verified: assets, routes, JavaScript and Vercel output are ready.');
