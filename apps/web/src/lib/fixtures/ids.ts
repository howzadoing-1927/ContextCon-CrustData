function fnv(seed: string, salt: number): string {
  let hash = 0x811c9dc5 ^ salt;
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}

function hexOf(seed: string, length: number): string {
  let out = "";
  for (let salt = 0; out.length < length; salt++) out += fnv(seed, salt);
  return out.slice(0, length);
}

/** Deterministic UUID-shaped id for fixture records. */
export function fid(seed: string): string {
  const h = hexOf(seed, 32);
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-4${h.slice(13, 16)}-a${h.slice(17, 20)}-${h.slice(20, 32)}`;
}

export function fsha(seed: string): string {
  return hexOf(`sha:${seed}`, 64);
}

export function fhex(seed: string, length: number): string {
  return hexOf(`hex:${seed}`, length);
}

const BASE = Date.parse("2026-11-05T18:05:00Z");

/** Fixture timestamp at `minutes` after the base mission start. */
export function at(minutes: number): string {
  return new Date(BASE + minutes * 60_000).toISOString().replace(".000Z", "Z");
}
