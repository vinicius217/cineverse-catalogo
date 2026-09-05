const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

// Exercise image failures and carousel state without external network requests.
const nodes = new Map();
const node = () => ({ style: {}, dataset: {}, classList: { toggle() {}, contains() { return false; } },
  addEventListener() {}, setAttribute() {}, matches() { return false; }, animate() {} });
const layers = [node(), node()];
const requests = [];
let tick;
const context = vm.createContext({
  URL, location: { href: 'http://localhost/' },
  localStorage: { getItem() { return null; } },
  matchMedia: () => ({ matches: false, addEventListener() {} }),
  document: { hidden: false, body: node(), addEventListener() {},
    querySelector(selector) { if (!nodes.has(selector)) nodes.set(selector, node()); return nodes.get(selector); },
    querySelectorAll(selector) { return selector === '.hero-backdrop' ? layers : []; } },
  setInterval(callback) { tick = callback; return 1; }, clearInterval() { tick = null; },
  Image: class {
    set src(value) {
      requests.push(value);
      queueMicrotask(() => value.includes('broken') || value.includes('SX1280') ? this.onerror() : this.onload());
    }
  }
});
const source = fs.readFileSync('app.js', 'utf8');
vm.runInContext(source.slice(0, source.indexOf('function apiUrl()')), context);
vm.runInContext(source.slice(source.indexOf('async function updateHero('), source.indexOf('async function openModal(')), context);
const run = code => vm.runInContext(code, context);

(async () => {
  const markup = run(`posterMarkup({title: '<Lost>', type: 'Filme', year: '2026', image: 'N/A'})`);
  assert.match(markup, /no-cover/);
  assert.match(markup, /&lt;Lost&gt;/);
  assert.doesNotMatch(markup, /<img/);
  const original = 'https://m.media-amazon.com/images/M/example._V1_SX300.jpg';
  assert.equal(await run(`heroPoster('${original}')`), original);
  assert.ok(requests.some(url => url.includes('SX1280')));
  run(`hero.items = [
    {id:'1', title:'First', image:'/good.jpg'},
    {id:'2', title:'Broken', image:'/broken.jpg'},
    {id:'3', title:'Third', image:'/third.jpg'}
  ]`);
  await run('updateHero(0)');
  assert.equal(nodes.get('.hero h1').textContent, 'First');
  await run('updateHero(1)');
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(nodes.get('.hero h1').textContent, 'Third');
  assert.equal(run('hero.items.length'), 2);
  run('scheduleHero()');
  assert.equal(typeof tick, 'function');
  run('hero.paused = true; scheduleHero()');
  assert.equal(tick, null);
  run('hero.paused = false; reducedMotion.matches = true; scheduleHero()');
  assert.equal(tick, null);
  console.log('Poster design, resolution fallback, carousel failure recovery, pause and reduced motion passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
