const assert = require('assert');

const {
  detectReportFileExt,
  getReportOpenFileType,
  isPdfHeader,
  safeReportFileName,
} = require('../dist/utils/reportPdf');

assert.strictEqual(detectReportFileExt('https://example.com/static/pdfs/a.PDF?x=1'), 'pdf');
assert.strictEqual(detectReportFileExt('/static/pdfs/a.txt'), 'unsupported');
assert.strictEqual(getReportOpenFileType('pdf'), 'pdf');
assert.strictEqual(getReportOpenFileType('unsupported'), undefined);
assert.strictEqual(isPdfHeader('%PDF-1.7'), true);
assert.strictEqual(isPdfHeader('{"detail":"not found"}'), false);
assert.strictEqual(
  safeReportFileName('RARE EARTH/DEEP PORE CLEANSING MASQUE', 'pdf'),
  'RARE_EARTH_DEEP_PORE_CLEANSING_MASQUE.pdf'
);

console.log('report pdf utils tests passed');
