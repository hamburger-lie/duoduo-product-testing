const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const wxml = fs.readFileSync(path.join(root, 'pages/report/report.wxml'), 'utf8');
const ts = fs.readFileSync(path.join(root, 'pages/report/report.ts'), 'utf8');

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

assert(wxml.includes('导出详细报告PDF'), 'report export button should say 导出详细报告PDF');
assert(!wxml.includes('导出 PDF'), 'old report export button copy should be removed');

assert(!ts.includes('wx.showActionSheet'), 'report export should not open an action sheet');
assert(!ts.includes('调研报告导出'), 'research report action sheet option should be removed');
assert(!ts.includes('白皮书导出'), 'whitepaper action sheet option should be removed');
assert(!ts.includes("mode=${encodeURIComponent('report')}"), 'report export mode should not be used');

assert(ts.includes('api.generateWhitepaper'), 'direct export should trigger whitepaper generation');
assert(ts.includes("mode=${encodeURIComponent('whitepaper')}"), 'direct export should open whitepaper mode');
assert(ts.includes('wx.navigateTo({ url: `/pages/webview/webview?url=${encodeURIComponent(wpUrl)}` })'), 'direct export should navigate to whitepaper viewer');

console.log('report export direct whitepaper checks passed');
