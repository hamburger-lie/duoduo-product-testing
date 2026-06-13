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

const wxml = read('pages/survey-review/survey-review.wxml');
const wxss = read('pages/survey-review/survey-review.wxss');
const ts = read('pages/survey-review/survey-review.ts');

assert(ts.includes('personasExpanded: false'), 'personas should be collapsed by default');
assert(ts.includes('onTogglePersonasExpanded()'), 'page should implement persona expand/collapse handler');
assert(wxml.includes('personasExpanded || index < 4'), 'persona list should render only first 4 by default');
assert(wxml.includes('persona-expand-btn'), 'persona section should render a bottom expand/collapse button');
assert(wxml.includes('展示更多'), 'expand button should use requested copy');
assert(wxml.includes('收起'), 'expanded state should use requested collapse copy');
assert(!wxml.includes('展开全部测品官'), 'expand button should not use old copy');
assert(!wxml.includes('收起测品官'), 'collapse button should not use old copy');
assert(wxml.includes('bind:tap="onTogglePersonasExpanded"'), 'expand button should bind toggle handler');
assert(wxss.includes('.persona-expand-btn'), 'expand button should have styling');
assert(
  !wxml.includes('<brand-loading size="small"></brand-loading>'),
  'survey generation inline state should not show the small brand loading icon'
);
assert(
  ts.includes('const QUESTION_READY_DELAY_MS = 300'),
  'survey review should show generated questions quickly after completion'
);
assert(
  !ts.includes('}, 1300);'),
  'survey review should not wait 1300ms after survey generation completes'
);

console.log('survey review persona collapse checks passed');
