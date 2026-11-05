const FALLBACK = ["UTC", "Asia/Kolkata", "Asia/Singapore", "Europe/London", "Europe/Berlin", "America/New_York", "America/Los_Angeles"];

export function timeZones(current?: string): string[] {
  let zones: string[] = FALLBACK;
  try {
    zones = (Intl as unknown as { supportedValuesOf(key: string): string[] }).supportedValuesOf("timeZone");
  } catch {}
  if (!zones.includes("UTC")) zones = ["UTC", ...zones];
  return current && !zones.includes(current) ? [current, ...zones] : zones;
}
