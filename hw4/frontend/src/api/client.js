/*
 * HTTP client of the REST API + the JWT session.
 *
 * The access and refresh tokens and the user profile live in localStorage (one tab
 * and the next page load see the same session). Every request sends
 * "Authorization: Bearer <access>". On a 401 the client exchanges the refresh token
 * for a new pair at /api/auth/refresh/ and retries the request once; if that fails
 * too, the session is cleared and the AuthContext asks the user to sign in.
 *
 * API_BASE is "" by default: the app calls "/api/..." on its own origin and nginx (or
 * the Vite dev server) proxies it to Django. Set VITE_API_URL to call the backend
 * directly across origins (CORS).
 */

export const API_BASE = (import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

const KEYS = { access: "rh.access", refresh: "rh.refresh", user: "rh.user" };

const store = {
  get(key) { try { return localStorage.getItem(key); } catch { return null; } },
  set(key, value) { try { localStorage.setItem(key, value); } catch { /* private mode */ } },
  del(key) { try { localStorage.removeItem(key); } catch { /* ignore */ } },
};

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data || {};
  }
}

// --- session -------------------------------------------------------------------------

const listeners = new Set();
function notify() { listeners.forEach((fn) => fn(session.user())); }

export const session = {
  user() { try { return JSON.parse(store.get(KEYS.user) || "null"); } catch { return null; } },
  access() { return store.get(KEYS.access); },
  isAuthed() { return Boolean(store.get(KEYS.access) && this.user()); },
  save({ access, refresh, user }) {
    if (access) store.set(KEYS.access, access);
    if (refresh) store.set(KEYS.refresh, refresh);
    if (user) store.set(KEYS.user, JSON.stringify(user));
    notify();
  },
  clear() { Object.values(KEYS).forEach((k) => store.del(k)); notify(); },
  // The payload of the access token (base64url JSON): exp, user_id, role, username ...
  claims(token = store.get(KEYS.access)) {
    try { return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))); } catch { return null; }
  },
  subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
};

// --- errors --------------------------------------------------------------------------

const label = (field) => field.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

// DRF errors: {"detail": "..."} for 401/403/404/409, {"field": ["message"]} for validation.
export function errorMessage(data, status) {
  if (typeof data.detail === "string") return data.detail;
  const field = Object.keys(data).find((k) => Array.isArray(data[k]) && data[k].length);
  if (field) return field === "non_field_errors" ? data[field][0] : `${label(field)}: ${data[field][0]}`;
  return status === 0 ? "Network error" : `HTTP ${status}`;
}

// --- requests ------------------------------------------------------------------------

export async function refreshTokens() {
  const refresh = store.get(KEYS.refresh);
  if (!refresh) return false;
  const res = await fetch(`${API_BASE}/api/auth/refresh/`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh }),
  });
  if (!res.ok) { session.clear(); return false; }
  session.save(await res.json()); // rotation: a new refresh token comes back, the old one is revoked
  return true;
}

/**
 * api("/api/lectures/", { method, body, auth })
 *   body  — an object (sent as JSON) or a FormData (multipart, for file uploads)
 *   auth  — false to skip the Authorization header on public endpoints
 */
export async function api(path, options = {}) {
  const { method = "GET", body, auth = true, _retry = true } = options;
  const headers = { Accept: "application/json" };
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  const access = store.get(KEYS.access);
  if (auth && access) headers.Authorization = `Bearer ${access}`;

  const url = path.startsWith("http") ? path : `${API_BASE}${path}`;
  let res;
  try {
    res = await fetch(url, { method, headers, body: body === undefined ? undefined : isForm ? body : JSON.stringify(body) });
  } catch {
    throw new ApiError("Network error — is the API running?", 0, {});
  }
  if (res.status === 204 || res.status === 205) return null;
  const data = await res.json().catch(() => ({}));

  if (res.status === 401 && auth && _retry && store.get(KEYS.refresh)) {
    if (await refreshTokens()) return api(path, { ...options, _retry: false });
  }
  if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status, data);
  return data;
}

// --- auth endpoints ------------------------------------------------------------------

export async function login(username, password) {
  const data = await api("/api/auth/login/", { method: "POST", body: { username, password }, auth: false });
  session.save(data);
  return data.user;
}

export async function register(payload) {
  const data = await api("/api/auth/register/", { method: "POST", body: payload, auth: false });
  session.save(data);
  return data.user;
}

export async function logout() {
  const refresh = store.get(KEYS.refresh);
  try { if (refresh) await api("/api/auth/logout/", { method: "POST", body: { refresh } }); } catch { /* already invalid */ }
  session.clear();
}

export async function reloadUser() {
  const user = await api("/api/auth/me/");
  session.save({ user });
  return user;
}
