const AVATAR_COUNT = 10;
const AVATAR_BASE = '/assets/persona-avatars/avatar-';

function hashText(text: string): number {
  let hash = 0;
  for (let i = 0; i < text.length; i++) {
    hash = ((hash << 5) - hash) + text.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function avatarSrcFor(personaId: string, personaKey: string, slot: number): string {
  if (slot >= 1 && slot <= AVATAR_COUNT) {
    return `${AVATAR_BASE}${String(slot).padStart(2, '0')}.png`;
  }
  const seed = personaId || personaKey || 'default';
  const idx = (hashText(seed) % AVATAR_COUNT) + 1;
  return `${AVATAR_BASE}${String(idx).padStart(2, '0')}.png`;
}

Component({
  properties: {
    personaKey: { type: String, value: 'yun' },
    personaId:  { type: String, value: '' },
    /** 直接指定头像编号 1-10，优先于 hash 计算，避免碰撞 */
    slot:       { type: Number, value: 0 },
    size:       { type: Number, value: 80 },
    ring:       { type: Boolean, value: false },
  },
  data: {
    imageSrc: '',
  },
  observers: {
    'personaId, personaKey, slot': function(personaId: string, personaKey: string, slot: number) {
      this.setData({ imageSrc: avatarSrcFor(personaId, personaKey, slot) });
    },
  },
  lifetimes: {
    attached() {
      this.setData({
        imageSrc: avatarSrcFor(
          this.properties.personaId,
          this.properties.personaKey,
          this.properties.slot,
        ),
      });
    },
  },
});
