const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..', '..');
const html = fs.readFileSync(path.join(root, 'backend/backend/whitepaper-static/index.html'), 'utf8');

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const overlayMatch = html.match(/<div class="pdf-success-overlay" id="pdfSuccessOverlay">[\s\S]*?<\/div>\s*<\/div>\s*<\/div>/);
assert(overlayMatch, 'PDF success overlay should exist');

const overlayHtml = overlayMatch[0];
assert(
  overlayHtml.includes('onclick="goToReportPdfs()"'),
  'PDF success confirm button should navigate to report PDF list'
);
assert(
  !overlayHtml.includes("onclick=\"document.getElementById('pdfSuccessOverlay').classList.remove('show')\""),
  'PDF success confirm button should not only close the overlay'
);
assert(
  html.includes('<script src="/whitepaper-static/jweixin-1.3.2.js"></script>'),
  'whitepaper viewer should load jweixin for wx.miniProgram APIs'
);
assert(
  /function\s+goToReportPdfs\s*\(\)\s*{[\s\S]*const targetUrl = '\/pages\/report-pdfs\/report-pdfs';[\s\S]*const bridgeUrl = '\/pages\/webview-bridge\/webview-bridge\?target=report-pdfs';[\s\S]*wx\.miniProgram\.navigateTo\(\{[\s\S]*url: targetUrl[\s\S]*wx\.miniProgram\.redirectTo\(\{[\s\S]*url: targetUrl[\s\S]*url: bridgeUrl/.test(html),
  'goToReportPdfs should navigate to /pages/report-pdfs/report-pdfs with redirect fallback'
);
assert(
  html.includes('/pdf-base64'),
  'WeChat PDF sync should use base64 endpoint'
);
assert(
  html.includes('new XMLHttpRequest()'),
  'WeChat PDF sync should use XMLHttpRequest'
);
assert(
  html.includes('xhr.timeout = 45000'),
  'WeChat PDF sync timeout should be capped at 45 seconds'
);
assert(
  html.includes('const PDF_JPEG_QUALITY = 0.82'),
  'PDF export should compress content screenshots to reduce upload size'
);

console.log('report PDF success navigation checks passed');
