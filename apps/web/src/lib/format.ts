const zoneAbbrev: Record<string, string> = { "Asia/Kolkata": "IST", UTC: "UTC" };

function zoneLabel(timeZone: string): string {
  return zoneAbbrev[timeZone] ?? timeZone;
}

export function formatInstant(iso: string | null | undefined, timeZone = "UTC"): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const text = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(date);
  return `${text} ${zoneLabel(timeZone)}`;
}

export function formatTime(iso: string | null | undefined, timeZone = "UTC"): string {
  if (!iso) return "—";
  const text = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  }).format(new Date(iso));
  return `${text} ${zoneLabel(timeZone)}`;
}

export function formatSlot(startIso: string, endIso: string, timeZone: string): string {
  const day = new Intl.DateTimeFormat("en-GB", { timeZone, weekday: "short", day: "numeric", month: "short" }).format(
    new Date(startIso),
  );
  const time = (iso: string) =>
    new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(new Date(iso));
  return `${day}, ${time(startIso)}–${time(endIso)} ${zoneLabel(timeZone)}`;
}

export function relativeAge(fromMs: number | null, nowMs: number): string {
  if (fromMs === null) return "never";
  const seconds = Math.max(0, Math.round((nowMs - fromMs) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds} s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h ago`;
  return `${Math.round(hours / 24)} d ago`;
}

export function shortId(value: string, length = 8): string {
  return value.length <= length + 1 ? value : `${value.slice(0, length)}…`;
}

export function humanize(token: string): string {
  const text = token.replace(/_/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function formatCount(value: number): string {
  return new Intl.NumberFormat("en-US").format(value);
}
