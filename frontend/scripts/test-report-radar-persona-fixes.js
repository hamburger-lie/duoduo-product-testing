const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const reportTs = fs.readFileSync(path.join(root, 'pages/report/report.ts'), 'utf8');
const reportWxss = fs.readFileSync(path.join(root, 'pages/report/report.wxss'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(reportTs.includes('function findHesitationSentence'), 'report should select hesitation from risk-like quote sentences');
assert(reportTs.includes('const riskText = personaHesitationText(score, risks);'), 'report should prefer structured risk text for hesitation');
assert(reportTs.includes('hesitation: compactVoiceText(riskText || findHesitationSentence(cleaned) || personaHesitationText(score, risks))'), 'report should not blindly use the second quote sentence as hesitation');

assert(reportWxss.includes('background: #FFFFFF;'), 'radar bubble should use an opaque white background');
assert(reportWxss.includes('z-index: 60;'), 'radar bubble should sit above hit areas and canvas');
assert(reportWxss.includes('pointer-events: auto;'), 'radar bubble should handle taps without passing through');

console.log('report radar/persona checks passed');
