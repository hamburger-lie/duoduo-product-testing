import type { EvaluationAnswer, PersonaSummary } from '../types/api';

const AVATAR_COUNT = 32;
const AVATAR_BASE = '/assets/persona-avatars/avatar-';
const STORAGE_PREFIX = 'persona_avatar_slot_';
const STORAGE_GENDER_PREFIX = 'persona_gender_';

type AvatarInput = {
  id?: string;
  avatar?: string;
  gender?: 'female' | 'male' | 'other';
  persona_tag?: string;
  name?: string;
};

export type AvatarDecorated<T> = T & {
  avatarSlot: number;
  avatarSrc: string;
};

function hashText(text: string): number {
  let hash = 0;
  for (let i = 0; i < text.length; i++) {
    hash = ((hash << 5) - hash) + text.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

export function avatarSrcForSlot(slot: number): string {
  const safeSlot = slot >= 1 && slot <= AVATAR_COUNT ? slot : 1;
  return `${AVATAR_BASE}${String(safeSlot).padStart(2, '0')}.png`;
}

function storageKey(personaId: string): string {
  return `${STORAGE_PREFIX}${personaId}`;
}

export function getStoredPersonaAvatarSlot(personaId: string): number {
  if (!personaId) return 0;
  try {
    const value = Number(wx.getStorageSync(storageKey(personaId)));
    return value >= 1 && value <= AVATAR_COUNT ? value : 0;
  } catch {
    return 0;
  }
}

export function rememberPersonaAvatarSlot(personaId: string, slot: number) {
  if (!personaId || slot < 1 || slot > AVATAR_COUNT) return;
  try {
    wx.setStorageSync(storageKey(personaId), slot);
  } catch {
    // Best effort only. Rendering can still use the computed slot.
  }
}

function rememberPersonaGender(personaId: string, gender: AvatarInput['gender']) {
  if (!personaId || !gender) return;
  try {
    wx.setStorageSync(`${STORAGE_GENDER_PREFIX}${personaId}`, gender);
  } catch {
    // Best effort only.
  }
}

function getStoredPersonaGender(personaId: string): AvatarInput['gender'] | undefined {
  if (!personaId) return undefined;
  try {
    const value = wx.getStorageSync(`${STORAGE_GENDER_PREFIX}${personaId}`);
    return value === 'male' || value === 'female' || value === 'other' ? value : undefined;
  } catch {
    return undefined;
  }
}

export function preferredSlots(gender?: AvatarInput['gender']): number[] {
  const all = Array.from({ length: AVATAR_COUNT }, (_, i) => i + 1);
  return all;
}

export function parseBackendAvatarSlot(avatar: string): number {
  const n = parseInt(avatar, 10);
  return Number.isInteger(n) && n >= 1 && n <= AVATAR_COUNT ? n : 0;
}

// Male slots: 5(男性护肤) 9(中年男性) 15(Z世代男) 16(直男) 18(运动男) 22(商务男) 25(外表男) 29(理工男)
function fixedSlotForRoleText(text: string): number {
  if (/男性护肤|结果导向|渠道运营/.test(text)) return 5;
  if (/中年男性|被动护肤|妻子推荐/.test(text)) return 9;
  if (/Z世代男|颜值经济|潮流尝鲜/.test(text)) return 15;
  if (/直男|礼品购买|给老婆买/.test(text)) return 16;
  if (/运动男性|控油清爽|形象管理/.test(text)) return 18;
  if (/商务形象男|送礼刚需/.test(text)) return 22;
  if (/外表导向男|抖音种草/.test(text)) return 25;
  if (/理工直男|护肤零基础/.test(text)) return 29;
  if (/学生党|小红书/.test(text)) return 4;
  if (/彩妆|尝鲜|线下零售/.test(text)) return 3;
  if (/性价比|家庭预算|直播间常客/.test(text)) return 2;
  if (/成分党|理性消费|一线城市白领/.test(text)) return 1;
  if (/敏感肌|成分避雷/.test(text)) return 8;
  if (/轻熟龄|抗老|功效派/.test(text)) return 6;
  if (/宝妈|母婴|新手妈妈/.test(text)) return 10;
  if (/小镇青年|社媒种草/.test(text)) return 7;
  return 0;
}

export function fixedSlotForPersona(persona: AvatarInput): number {
  const backendSlot = parseBackendAvatarSlot(persona.avatar || '');
  if (backendSlot) return backendSlot;
  return fixedSlotForRoleText(`${persona.persona_tag || ''} ${persona.name || ''}`);
}

function seedForPersona(persona: AvatarInput, fallback = ''): string {
  return persona.id || persona.avatar || persona.persona_tag || persona.name || fallback || 'persona';
}

function chooseSlot(persona: AvatarInput, used: Set<number>, fallbackIndex: number): number {
  const fixedSlot = fixedSlotForPersona(persona);
  if (fixedSlot && !used.has(fixedSlot)) return fixedSlot;

  const stored = getStoredPersonaAvatarSlot(persona.id || '');
  if (stored && !used.has(stored)) return stored;

  const gender = persona.gender || getStoredPersonaGender(persona.id || '');
  const slots = preferredSlots(gender);
  const start = hashText(seedForPersona(persona, String(fallbackIndex))) % slots.length;
  for (let offset = 0; offset < slots.length; offset++) {
    const candidate = slots[(start + offset) % slots.length];
    if (!used.has(candidate)) return candidate;
  }

  return slots[start] || ((fallbackIndex % AVATAR_COUNT) + 1);
}

export function decoratePersonasWithAvatars<T extends PersonaSummary>(
  personas: T[],
): Array<AvatarDecorated<T> & { selected: boolean }> {
  const used = new Set<number>();
  return personas.map((persona, index) => {
    const avatarSlot = chooseSlot(persona, used, index);
    used.add(avatarSlot);
    rememberPersonaAvatarSlot(persona.id, avatarSlot);
    rememberPersonaGender(persona.id, persona.gender);
    return {
      ...persona,
      selected: false,
      avatarSlot,
      avatarSrc: avatarSrcForSlot(avatarSlot),
    };
  });
}

export function avatarSlotForPersona(
  personaId: string,
  fallbackIndex = 0,
  used?: Set<number>,
  persona?: AvatarInput,
): number {
  const taken = used || new Set<number>();
  const slot = chooseSlot({ ...persona, id: personaId || persona?.id }, taken, fallbackIndex);
  if (used) used.add(slot);
  rememberPersonaAvatarSlot(personaId, slot);
  return slot;
}

export function decorateAnswersWithAvatarSlots<T extends EvaluationAnswer>(
  answers: T[],
): Array<T & { avatarSlot: number; avatarSrc: string }> {
  const used = new Set<number>();
  return answers.map((answer, index) => {
    const snapshot = (answer as any).persona_snapshot || {};
    const avatarSlot = avatarSlotForPersona(answer.persona_id, index, used, {
      id: answer.persona_id,
      avatar: (answer as any).avatar || snapshot.avatar,
      persona_tag: answer.persona_tag || snapshot.persona_tag,
      name: answer.persona_name || snapshot.name,
      gender: snapshot.gender,
    });
    return {
      ...answer,
      avatarSlot,
      avatarSrc: avatarSrcForSlot(avatarSlot),
    };
  });
}
