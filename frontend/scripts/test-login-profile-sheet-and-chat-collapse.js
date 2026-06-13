const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const homeTs = fs.readFileSync(path.join(root, 'pages/home/home.ts'), 'utf8');
const chatTs = fs.readFileSync(path.join(root, 'pages/chat/chat.ts'), 'utf8');
const chatWxml = fs.readFileSync(path.join(root, 'pages/chat/chat.wxml'), 'utf8');
const bubbleTs = fs.readFileSync(path.join(root, 'components/bubble-speak/bubble-speak.ts'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(homeTs.includes('user.is_new_user'), 'home login profile sheet should account for backend new-user flag');
assert(homeTs.includes('!user.avatar_url'), 'home login profile sheet should show when avatar is missing');

assert(
  chatWxml.includes('defaultQaAnswersCollapsed="{{item.qaAnswersCollapsed || false}}"'),
  'chat page should pass the per-turn default answer collapse state to bubble-speak',
);
assert(
  bubbleTs.includes('defaultQaAnswersCollapsed') && bubbleTs.includes('qaAnswersCollapsed: this.properties.defaultQaAnswersCollapsed'),
  'bubble-speak should initialize qa answer collapse state from a property',
);
assert(
  chatTs.includes('qaAnswersCollapsed: true'),
  'completed persona turns should mark QA answers collapsed after output finishes',
);

console.log('login profile sheet and chat collapse checks passed');
