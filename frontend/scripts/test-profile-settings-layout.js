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

const settingsWxml = read('pages/settings/settings.wxml');
const settingsTs = read('pages/settings/settings.ts');
const settingsJson = read('pages/settings/settings.json');
const profileWxml = read('pages/profile/profile.wxml');
const profileTs = read('pages/profile/profile.ts');
const apiTs = read('services/api.ts');

assert(!settingsWxml.includes('当前版本'), 'settings page should not show current version');
assert(!settingsWxml.includes('{{version}}'), 'settings page should not bind version');
assert(!settingsTs.includes('version:'), 'settings page data should not define version');
assert(!settingsWxml.includes('logout-btn'), 'settings page should not show logout button');
assert(!settingsWxml.includes('bind:tap="onTapLogout"'), 'settings page should not bind logout');
assert(!settingsWxml.includes('用户协议'), 'settings page should not show user agreement');
assert(!settingsTs.includes('onTapAgreement'), 'settings page should not implement user agreement');
assert(!settingsTs.includes('openPrivacyContract'), 'privacy policy should render in app instead of opening external contract');
assert(settingsJson.includes('隐私政策'), 'settings page title should be privacy policy');
assert(settingsWxml.includes('隐私政策'), 'settings page should render privacy policy content');
assert(settingsWxml.includes('信息收集与使用'), 'privacy policy should include content sections');
assert(!profileWxml.includes('<view class="menu-label">设置</view>'), 'profile menu should not show settings');
assert(!profileWxml.includes('我的测品官'), 'profile persona menu should not use old copy');
assert(profileWxml.includes('测品官阵容'), 'profile persona menu should use requested copy');
assert(!profileWxml.includes('我的积分'), 'profile credits menu should not use old copy');
assert(profileWxml.includes('积分使用记录'), 'profile credits menu should use requested copy');
assert(profileWxml.includes('隐私政策'), 'profile menu should show privacy policy');
assert(profileWxml.includes('bind:tap="onTapPrivacyPolicy"'), 'profile privacy item should bind onTapPrivacyPolicy');
assert(!profileTs.includes('onTapSettings'), 'profile page should not implement settings navigation');
assert(profileTs.includes('onTapPrivacyPolicy()'), 'profile page should implement privacy policy navigation');
assert(profileWxml.includes('退出登录'), 'profile page should show logout');
assert(profileWxml.includes('bind:tap="onTapLogout"'), 'profile logout should bind onTapLogout');
assert(profileTs.includes('onTapLogout()'), 'profile page should implement onTapLogout');
assert(profileTs.includes('api.logout()'), 'profile logout should call backend logout API');
assert(apiTs.includes('async logout()'), 'api adapter should expose logout');
assert(apiTs.includes('E.AUTH_LOGOUT'), 'api logout should use AUTH_LOGOUT endpoint');

console.log('profile/settings layout checks passed');
