const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const wxml = fs.readFileSync(path.join(root, 'pages/personas/personas.wxml'), 'utf8');
const wxss = fs.readFileSync(path.join(root, 'pages/personas/personas.wxss'), 'utf8');
const ts = fs.readFileSync(path.join(root, 'pages/personas/personas.ts'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(!wxml.includes('新建'), 'personas page should not show the create button');
assert(!wxml.includes('立即创建'), 'personas empty state should not show a create action');
assert(!wxml.includes('delete-btn'), 'personas page should not render trash buttons');
assert(!wxml.includes('onDeletePersona'), 'personas page should not bind delete actions');
assert(!wxml.includes('onTapCreate'), 'personas page should not bind create actions');

assert(!wxss.includes('.create-btn'), 'unused create button styles should be removed');
assert(!wxss.includes('.empty-btn'), 'unused empty create styles should be removed');
assert(!wxss.includes('.delete-btn'), 'unused trash button styles should be removed');

assert(!ts.includes('onTapCreate()'), 'create handler should be removed');
assert(!ts.includes('onDeletePersona'), 'delete handler should be removed');
assert(!ts.includes('deletePersona'), 'persona delete API should not be called from the list page');

console.log('personas readonly list checks passed');
