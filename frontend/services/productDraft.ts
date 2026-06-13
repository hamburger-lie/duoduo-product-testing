export interface ProductCreationDraft {
  id: string;
  name: string;
  description: string;
  imagePaths: string[];
  createdAt: number;
}

const PREFIX = 'product_creation_draft_';

function imageMimeType(filePath: string): string {
  const ext = filePath.split('.').pop()?.split('?')[0]?.toLowerCase();
  return ext === 'png' ? 'image/png' : 'image/jpeg';
}

function readImageAsDataUrl(filePath: string): Promise<string | null> {
  return new Promise(resolve => {
    wx.getFileSystemManager().readFile({
      filePath,
      encoding: 'base64',
      success: (res: any) => {
        const base64 = String(res.data || '');
        resolve(base64 ? `data:${imageMimeType(filePath)};base64,${base64}` : null);
      },
      fail: () => resolve(null),
    });
  });
}

export async function readProductImageBase64List(filePaths: string[]): Promise<string[]> {
  const images = await Promise.all(filePaths.slice(0, 5).map(readImageAsDataUrl));
  return images.filter((item): item is string => Boolean(item));
}

export function shortProductName(name: string): string {
  return Array.from(String(name || '').trim()).slice(0, 10).join('');
}

export function saveProductCreationDraft(input: {
  name: string;
  description: string;
  imagePaths: string[];
}): ProductCreationDraft {
  const draft: ProductCreationDraft = {
    id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    name: input.name,
    description: input.description,
    imagePaths: input.imagePaths.slice(0, 5),
    createdAt: Date.now(),
  };
  wx.setStorageSync(PREFIX + draft.id, draft);
  return draft;
}

export function takeProductCreationDraft(id: string): ProductCreationDraft | null {
  if (!id) return null;
  const key = PREFIX + id;
  const draft = wx.getStorageSync(key) as ProductCreationDraft | '';
  wx.removeStorageSync(key);
  return draft || null;
}
