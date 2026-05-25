import { avatarSlotForPersona, avatarSrcForSlot, parseBackendAvatarSlot } from '../../utils/personaAvatar';

function avatarSrcFor(personaId: string, personaKey: string, slot: number): string {
  if (slot >= 1) return avatarSrcForSlot(slot);
  const backendSlot = parseBackendAvatarSlot(personaKey || '');
  if (backendSlot) return avatarSrcForSlot(backendSlot);
  return avatarSrcForSlot(avatarSlotForPersona(personaId || personaKey || 'default'));
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
    // Guard: observers fire before `attached` during init; skip setData until mounted
    'personaId, personaKey, slot': function(personaId: string, personaKey: string, slot: number) {
      if (!(this as any)._attached) return;
      this.setData({ imageSrc: avatarSrcFor(personaId, personaKey, slot) });
    },
  },
  lifetimes: {
    attached() {
      (this as any)._attached = true;
      this.setData({
        imageSrc: avatarSrcFor(
          this.properties.personaId,
          this.properties.personaKey,
          this.properties.slot,
        ),
      });
    },
    detached() {
      (this as any)._attached = false;
    },
  },
});
