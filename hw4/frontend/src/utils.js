/* Formatting helpers shared by the pages */

export const fmtTime = (iso) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
export const fmtDate = (iso) => new Date(iso).toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" });
export const fmtDateTime = (iso) => `${fmtDate(iso)} ${fmtTime(iso)}`;
export const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

export function initials(user) {
  const name = (user.display_name || user.username || "?").trim();
  const parts = name.split(/\s+/);
  return (parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2)).toUpperCase();
}

// colour class of a topic chip: topics get t0..t7 in plan order
export function topicIndex(topics, id) {
  const i = (topics || []).findIndex((t) => t.id === id);
  return i < 0 ? 0 : i % 8;
}

// Field errors from DRF ({"field": ["message"]}) -> {field: "message"}; only fields the form knows
export function fieldErrors(data, fields) {
  const out = {};
  for (const name of fields) if (Array.isArray(data?.[name]) && data[name].length) out[name] = data[name][0];
  return out;
}

export const REFRESH_MS = Math.max(1000, Number(import.meta.env.VITE_REFRESH_MS) || 3000);
