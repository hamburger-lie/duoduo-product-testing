const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const wxml = fs.readFileSync(path.join(root, 'pages/credits/credits.wxml'), 'utf8');
const ts = fs.readFileSync(path.join(root, 'pages/credits/credits.ts'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(!wxml.includes('充值积分'), 'credits page should not show recharge section title');
assert(!wxml.includes('立即充值'), 'credits page should not show recharge action');
assert(!wxml.includes('积分用于发起 AI 调研'), 'credits page should not show recharge tip');
assert(!wxml.includes('recharge-section'), 'credits page should not render recharge section');
assert(wxml.includes('tx-list'), 'credits page should keep transaction list');
assert(wxml.includes("{{item.isIncome ? '+' : ''}}{{item.amount}}"), 'credits page should keep income/expense amount display');

assert(!ts.includes('rechargeCredits'), 'credits page should not keep recharge API call');
assert(!ts.includes('onRecharge'), 'credits page should not keep recharge handler');
assert(!ts.includes('onSelectAmount'), 'credits page should not keep amount selection handler');

console.log('credits usage records only checks passed');
