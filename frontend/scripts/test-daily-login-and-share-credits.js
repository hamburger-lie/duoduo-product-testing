const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const shareWxml = fs.readFileSync(path.join(root, 'pages/share-invite/share-invite.wxml'), 'utf8');
const homeWxml = fs.readFileSync(path.join(root, 'pages/home/home.wxml'), 'utf8');
const homeTs = fs.readFileSync(path.join(root, 'pages/home/home.ts'), 'utf8');
const apiTs = fs.readFileSync(path.join(root, 'services/api.ts'), 'utf8');
const endpointsTs = fs.readFileSync(path.join(root, 'services/endpoints.ts'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

[
  '+20 积分',
  '每日登录直接到账',
  '+10 积分',
  '1 位 = 1 积分',
  '导出详细报告 PDF 消耗',
  '5 积分',
  '50 积分',
].forEach(text => {
  assert(shareWxml.includes(text), `share page should include: ${text}`);
});
assert(!shareWxml.includes('发起一套 AI 调研消耗'), 'share page should remove old fixed survey cost copy');

assert(endpointsTs.includes("CREDIT_DAILY_LOGIN:        '/credits/daily-login'"), 'daily login endpoint should be defined');
assert(apiTs.includes('claimDailyLoginCredits'), 'API should expose daily login claim');
assert(apiTs.includes('method: \'POST\''), 'daily login claim should POST');
assert(homeTs.includes('this.claimDailyLoginCredits();'), 'home should claim daily login credits');
assert(homeWxml.includes('showDailyCreditModal'), 'home should render daily credit modal');
assert(homeWxml.includes('每日登录奖励'), 'home modal should use daily login reward title');
assert(homeWxml.includes('已直接到账'), 'home modal should say credits arrived directly');

console.log('daily login and share credits checks passed');
