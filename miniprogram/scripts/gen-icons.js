'use strict';
const zlib = require('zlib');
const fs   = require('fs');

// ── CRC32 ──────────────────────────────────────────────────────────────────────
const CRC_TABLE = (() => {
  const t = [];
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = (c & 1) ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    t.push(c >>> 0);
  }
  return t;
})();
function crc32(buf) {
  let c = 0xFFFFFFFF;
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xFF] ^ (c >>> 8);
  return (c ^ 0xFFFFFFFF) >>> 0;
}

// ── PNG builder ────────────────────────────────────────────────────────────────
function makePng(W, H, pixels) {
  function chunk(type, data) {
    const tb  = Buffer.from(type, 'ascii');
    const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
    const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(Buffer.concat([tb, data])));
    return Buffer.concat([len, tb, data, crc]);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(W, 0); ihdr.writeUInt32BE(H, 4);
  ihdr[8] = 8; ihdr[9] = 6; // 8-bit RGBA

  const raw = Buffer.alloc(H * (1 + W * 4));
  let o = 0;
  for (let y = 0; y < H; y++) {
    raw[o++] = 0;
    for (let x = 0; x < W; x++) {
      const p = pixels[y * W + x] >>> 0;
      raw[o++] = (p >>> 24) & 0xFF;
      raw[o++] = (p >>> 16) & 0xFF;
      raw[o++] = (p >>>  8) & 0xFF;
      raw[o++] =  p         & 0xFF;
    }
  }
  return Buffer.concat([
    Buffer.from([137,80,78,71,13,10,26,10]),
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

// ── Pixel helpers ──────────────────────────────────────────────────────────────
const W = 40, H = 40;
const T = 0;

function rgba(r, g, b, a = 255) {
  return (r * 0x1000000 + g * 0x10000 + b * 0x100 + a) >>> 0;
}

function icon(fn) {
  const px = new Uint32Array(W * H);
  for (let y = 0; y < H; y++)
    for (let x = 0; x < W; x++)
      px[y * W + x] = fn(x, y) >>> 0;
  return px;
}

const GRAY = rgba(140, 140, 140);
const PURP = rgba(123, 111, 168);

// ── Icon shapes ────────────────────────────────────────────────────────────────
function homeIcon(c) {
  return icon((x, y) => {
    const cx = 20;
    // Roof: peak (cx,7) → base y=22, half-width 0→12
    if (y >= 7 && y <= 22) {
      const hw = Math.round((y - 7) * 12 / 15);
      if (x >= cx - hw && x <= cx + hw) return c;
    }
    // Walls + floor: y=22-33, x=8-32, with door cutout
    if (y >= 22 && y <= 33 && x >= 8 && x <= 32) {
      if (y >= 25 && x >= 16 && x <= 24) return T; // door gap
      return c;
    }
    return T;
  });
}

function archiveIcon(c) {
  return icon((x, y) => {
    // Folder tab: y=10-16, x=6-19
    if (y >= 10 && y <= 16 && x >= 6 && x <= 19) return c;
    // Folder body: y=14-33, x=6-34 (filled)
    if (y >= 14 && y <= 33 && x >= 6 && x <= 34) return c;
    return T;
  });
}

function profileIcon(c) {
  return icon((x, y) => {
    const cx = 20;
    // Head: circle (cx,13) r=7
    if ((x - cx) ** 2 + (y - 13) ** 2 <= 49) return c;
    // Body: widens from y=23 downward
    if (y >= 23 && y <= 35) {
      const hw = Math.min(5 + (y - 23) * 1.3, 13);
      if (Math.abs(x - cx) <= hw) return c;
    }
    return T;
  });
}

// ── Write files ────────────────────────────────────────────────────────────────
const OUT = require('path').join(__dirname, '..', 'assets');
const files = [
  ['tab-home.png',        homeIcon(GRAY)],
  ['tab-home-act.png',    homeIcon(PURP)],
  ['tab-archive.png',     archiveIcon(GRAY)],
  ['tab-archive-act.png', archiveIcon(PURP)],
  ['tab-profile.png',     profileIcon(GRAY)],
  ['tab-profile-act.png', profileIcon(PURP)],
];
for (const [name, pixels] of files) {
  fs.writeFileSync(`${OUT}\\${name}`, makePng(W, H, pixels));
  console.log('created:', name);
}
