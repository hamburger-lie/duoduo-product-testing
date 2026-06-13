const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');

function read(relativePath) {
  return fs.readFileSync(path.join(root, relativePath), 'utf8');
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const componentWxml = read('components/brand-loading/brand-loading.wxml');
const componentWxss = read('components/brand-loading/brand-loading.wxss');
const componentJson = read('components/brand-loading/brand-loading.json');

assert(fs.existsSync(path.join(root, 'assets/cibe-mark.png')), 'cropped CIBE mark asset should exist');
assert(componentJson.includes('"component": true'), 'brand-loading should be a component');
assert(componentWxml.includes('/assets/cibe-mark.png'), 'brand-loading should render CIBE mark');
assert(!componentWxml.includes('CIBE'), 'brand-loading should not render text');
assert(!componentWxml.includes('美博会'), 'brand-loading should not render text');
assert(componentWxss.includes('brandLoadingPulseSpin'), 'brand-loading should have pulse/spin animation');
assert(componentWxss.includes('rotate(7deg)'), 'brand-loading should gently rotate');
assert(componentWxss.includes('scale(1.04)'), 'brand-loading should gently breathe');

const pages = [
  'survey-review',
  'personas',
  'credits',
  'products',
  'persona-edit',
  'report-pdfs',
  'product-detail',
  'history',
  'orders',
];

for (const page of pages) {
  const pageDir = `pages/${page}`;
  const wxml = read(`${pageDir}/${page}.wxml`);
  const json = read(`${pageDir}/${page}.json`);
  assert(json.includes('"brand-loading"'), `${page} should register brand-loading`);
  assert(json.includes('/components/brand-loading/brand-loading'), `${page} should point to brand-loading component`);
  assert(wxml.includes('<brand-loading'), `${page} loading state should use brand-loading`);
  assert(!wxml.includes('loading-dot-wrap'), `${page} should not render old dot loader`);
  assert(!wxml.includes('加载中…'), `${page} should not render loading text`);
}

const allPageText = pages
  .map(page => read(`pages/${page}/${page}.wxml`) + read(`pages/${page}/${page}.wxss`))
  .join('\n');
assert(!allPageText.includes('loading-dot-wrap'), 'old dot loader styles should be removed from covered pages');

console.log('brand loading checks passed');
