import { api } from '../services/api';
import type { User } from '../types/api';

const TOKEN_KEY = 'auth_token';
const USER_KEY = 'current_user';

export function hasToken(): boolean {
  try {
    return !!wx.getStorageSync(TOKEN_KEY);
  } catch {
    return false;
  }
}

export function getStoredUser(): User | null {
  try {
    const raw = wx.getStorageSync(USER_KEY);
    return raw || null;
  } catch {
    return null;
  }
}

export function clearAuth(): void {
  try {
    wx.removeStorageSync(TOKEN_KEY);
    wx.removeStorageSync(USER_KEY);
  } catch {
    // ignore storage failures
  }
}

function wxLogin(): Promise<string> {
  return new Promise((resolve, reject) => {
    wx.login({
      success: res => {
        if (res.code) {
          resolve(res.code);
          return;
        }
        reject(new Error('wx.login returned empty code'));
      },
      fail: reject,
    });
  });
}

export async function loginWithPhoneCode(phoneCode: string): Promise<User> {
  const code = await wxLogin();
  const res = await api.loginWithPhone(code, phoneCode);
  wx.setStorageSync(TOKEN_KEY, res.token);
  wx.setStorageSync(USER_KEY, res.user);
  wx.removeStorageSync('manual_logout');
  wx.removeStorageSync('referral_code');
  return res.user;
}

