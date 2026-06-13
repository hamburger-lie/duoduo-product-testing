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

function extractRule(css, selector) {
  const match = css.match(new RegExp(`${selector.replace('.', '\\.')}\\s*\\{([\\s\\S]*?)\\}`));
  return match ? match[1] : '';
}

function prop(rule, name) {
  const match = rule.match(new RegExp(`${name}\\s*:\\s*([^;]+);`));
  return match ? match[1].trim() : '';
}

const wxml = read('pages/create/create.wxml');
const wxss = read('pages/create/create.wxss');
const ts = read('pages/create/create.ts');
const sectionTitle = extractRule(wxss, '.section-title');
const fieldLabel = extractRule(wxss, '.field-label');
const extractKicker = extractRule(wxss, '.extract-card-kicker');
const extractTitle = extractRule(wxss, '.extract-card-title');

assert(!wxml.includes('AI识图填表'), 'top AI image form label should be removed');
assert(!wxml.includes('选填'), 'optional copy should be removed from product image header');
assert(!wxml.includes('✨ AI识别并填充'), 'AI extract title should not include emoji or old copy');
assert(!wxml.includes('自动提取产品名、卖点、成分、价格等信息'), 'AI extract subtitle should be removed');
assert(!wxml.includes('部分内容识别不确定，请手动确认'), 'extract notice should not show duplicate low-confidence copy');
assert(!wxml.includes('识别不确定，请确认或修改'), 'field warning should not use old low-confidence copy');
assert(!wxml.includes('已从图片识别'), 'AI field badge should not use old copy');
assert(!wxml.includes('已自动填入'), 'AI field badge should not use previous copy');
assert(wxml.includes('已同步解析内容'), 'AI field badge should use requested copy');
assert(!wxml.includes('AI生成也会犯错，仅供参考'), 'field warning should not use previous AI disclaimer copy');
assert(!wxml.includes('AI生成仅供参考'), 'field warning should be removed');
assert(!wxml.includes('field-warn-text'), 'field warning element should be removed');
assert(!wxml.includes('解析图片并自动填充产品信息'), 'AI extract title should not use the previous one-line copy');
assert(wxml.includes('<text class="extract-card-kicker">点击</text>'), 'AI extract card should render click prompt on the first line');
assert(wxml.includes('<text class="extract-card-title">自动解析图片并填充信息</text>'), 'AI extract card should render requested copy on the second line');
assert(!wxml.includes('extract-card-sub'), 'AI extract card should not render small subtitle text');
assert(wxml.includes('extract-progress-msg'), 'extracting state should show a status message');
assert(wxml.includes('extract-progress-track'), 'extracting state should show a progress bar');
assert(wxml.includes('extract-progress-fill'), 'extracting state should show progress fill');
assert(wxml.includes('{{extractProgress}}%'), 'extracting state should render progress percentage');
assert(wxml.includes('wx:if="{{!extractDone}}" class="extract-card"'), 'AI extract card should show before extraction is done');
assert(wxml.includes('class="extract-card" bind:tap="onTapExtractCard"'), 'AI extract card should use the page-level tap handler');
assert(wxml.indexOf('class="extract-card"') > wxml.indexOf('class="upload-zone"'), 'AI extract card should be below the upload area');
assert(wxml.indexOf('class="extract-card"') < wxml.indexOf('class="field-card"'), 'AI extract card should be above product form fields');
assert(ts.includes('onTapExtractCard()'), 'create page should implement extract card tap handler');
assert(ts.includes('请先上传产品图'), 'tap handler should prompt when no image has been uploaded');
assert(ts.includes('extractProgress'), 'create page should track image extraction progress');
assert(ts.includes('extractMsg'), 'create page should track image extraction status');
assert(ts.includes('_setExtractProgress'), 'create page should update extraction progress by stage');
assert(ts.includes('_animateExtractTo'), 'create page should animate extraction progress while waiting');
assert(ts.includes('_stopExtractProgress'), 'create page should stop extraction progress animation');
assert(ts.includes('上传图片中'), 'extract flow should show upload status');
assert(ts.includes('AI 正在分析图片'), 'extract flow should show AI analysis status');
assert(ts.includes('正在填充产品信息'), 'extract flow should show form fill status');

assert(prop(extractKicker, 'font-size') === prop(extractTitle, 'font-size'), 'extract card lines should share font size');
assert(prop(extractKicker, 'font-weight') === prop(extractTitle, 'font-weight'), 'extract card lines should share font weight');
assert(prop(extractKicker, 'color') === prop(extractTitle, 'color'), 'extract card lines should share color');

assert(prop(fieldLabel, 'font-size') === prop(sectionTitle, 'font-size'), 'field labels should match product image title font size');
assert(prop(fieldLabel, 'font-weight') === prop(sectionTitle, 'font-weight'), 'field labels should match product image title weight');
assert(prop(fieldLabel, 'color') === prop(sectionTitle, 'color'), 'field labels should match product image title color');

console.log('create page copy checks passed');
