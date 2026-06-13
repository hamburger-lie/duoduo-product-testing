const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const shareInviteJson = JSON.parse(
  fs.readFileSync(path.join(root, 'pages/share-invite/share-invite.json'), 'utf8')
);
const projectConfig = JSON.parse(
  fs.readFileSync(path.join(root, 'project.config.json'), 'utf8')
);

assert(
  !Object.prototype.hasOwnProperty.call(shareInviteJson, 'enableShareTimeline'),
  'share-invite page.json should not include invalid enableShareTimeline'
);

const ignoredFolders = new Set(
  (projectConfig.packOptions?.ignore || [])
    .filter(item => item.type === 'folder')
    .map(item => item.value)
);
assert(ignoredFolders.has('scripts'), 'project.config.json should ignore scripts folder');
assert(ignoredFolders.has('dist'), 'project.config.json should ignore dist folder');

const sourceDirs = ['pages', 'components', 'services', 'utils', 'types', 'mocks'];
for (const dir of sourceDirs) {
  const dirPath = path.join(root, dir);
  if (!fs.existsSync(dirPath)) continue;
  const stack = [dirPath];
  while (stack.length) {
    const current = stack.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(fullPath);
        continue;
      }
      if (!/\.(ts|js|wxml|json)$/.test(entry.name)) continue;
      const content = fs.readFileSync(fullPath, 'utf8');
      assert(
        !content.includes('/dist/') && !content.includes('../dist') && !content.includes('../../dist'),
        `${path.relative(root, fullPath)} should not reference generated dist files`
      );
    }
  }
}

console.log('miniprogram build config checks passed');
