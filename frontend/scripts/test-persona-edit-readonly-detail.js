const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const wxml = fs.readFileSync(path.join(root, 'pages/persona-edit/persona-edit.wxml'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(!wxml.includes('保存修改'), 'persona detail should not show save changes copy');
assert(!wxml.includes('bind:tap="onSave"'), 'persona detail should not render the save button tap handler');
assert(!wxml.includes('save-btn'), 'persona detail should not render the save button block');

console.log('persona edit readonly detail checks passed');
