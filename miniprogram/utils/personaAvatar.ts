import type { EvaluationAnswer, PersonaSummary } from '../types/api';

const AVATAR_COUNT = 10;
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
  if (gender === 'male') return [6, 7, 8, 9, 10, 1, 2, 3, 4, 5];
  if (gender === 'female') return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  return [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
}

export function parseBackendAvatarSlot(avatar: string): number {
  const n = parseInt(avatar, 10);
  return n >= 1 && n <= AVATAR_COUNT ? n : 0;
}

function fixedSlotForRoleText(text: string): number {
  if (/\u7537\u6027|\u7537\u58eb|\u7537/.test(text)) return 7;
  if (/\u5b66\u751f|\u5c0f\u7ea2\u4e66/.test(text)) return 1;
  if (/\u5f69\u5986|\u5c1d\u9c9c|\u989c\u503c|\u5305\u88c5|\u7ebf\u4e0b\u96f6\u552e/.test(text)) return 2;
  if (/\u6027\u4ef7\u6bd4|\u5bb6\u5ead|\u9884\u7b97|\u5b9d\u5988|\u5988\u5988|\u6bcd\u5a74/.test(text)) return 5;
  if (/\u6210\u5206|\u7406\u6027\u6d88\u8d39|\u4e00\u7ebf\u57ce\u5e02/.test(text)) return 4;
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
