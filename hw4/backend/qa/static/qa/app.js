/*
 * Raise Hand — browser client of the REST API.
 *
 * Session: the access/refresh tokens and the user profile live in localStorage.
 * Every API call sends "Authorization: Bearer <access>". On a 401 the client
 * exchanges the refresh token for a new pair at /api/auth/refresh/ and retries
 * once; if that fails too, the session is cleared and the page asks to sign in.
 */

const RH = (() => {
  const KEYS = { access: "rh.access", refresh: "rh.refresh", user: "rh.user", theme: "rh.theme" };
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch { /* private mode */ } },
    del(key) { try { localStorage.removeItem(key); } catch { /* ignore */ } },
  };

  class ApiError extends Error {
    constructor(message, status, data) { super(message); this.status = status; this.data = data || {}; }
  }

  const RH = {
    refreshMs: 3000,
    ApiError,

    // ---------------------------------------------------------------- session
    user() { try { return JSON.parse(store.get(KEYS.user) || "null"); } catch { return null; } },
    isAuthed() { return Boolean(store.get(KEYS.access) && this.user()); },
    saveSession({ access, refresh, user }) {
      if (access) store.set(KEYS.access, access);
      if (refresh) store.set(KEYS.refresh, refresh);
      if (user) store.set(KEYS.user, JSON.stringify(user));
      this.renderNav();
    },
    clearSession() { Object.values(KEYS).slice(0, 3).forEach((k) => store.del(k)); this.renderNav(); },
    tokenClaims(token = store.get(KEYS.access)) {
      try { return JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/"))); } catch { return null; }
    },
    hasRole(...roles) { const u = this.user(); return Boolean(u && roles.includes(u.role)); },
    canCreateLectures() { return this.hasRole("lecturer", "admin"); },

    // -------------------------------------------------------------------- api
    async api(path, options = {}) {
      const { method = "GET", body, auth = true, _retry = true } = options;
      const headers = { Accept: "application/json" };
      if (body !== undefined) headers["Content-Type"] = "application/json";
      const access = store.get(KEYS.access);
      if (auth && access) headers.Authorization = `Bearer ${access}`;

      const res = await fetch(path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
      if (res.status === 204 || res.status === 205) return null;
      const data = await res.json().catch(() => ({}));

      if (res.status === 401 && auth && _retry && store.get(KEYS.refresh)) {
        const refreshed = await this.refreshTokens();
        if (refreshed) return this.api(path, { ...options, _retry: false });
      }
      if (!res.ok) throw new ApiError(this.errorMessage(data, res.status), res.status, data);
      return data;
    },

    async refreshTokens() {
      const refresh = store.get(KEYS.refresh);
      if (!refresh) return false;
      const res = await fetch("/api/auth/refresh/", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ refresh }),
      });
      if (!res.ok) { this.clearSession(); return false; }
      const data = await res.json();
      this.saveSession(data);  // rotation: a new refresh token comes back, the old one is revoked
      return true;
    },

    async login(username, password) {
      const data = await this.api("/api/auth/login/", { method: "POST", body: { username, password }, auth: false });
      this.saveSession(data);
      return data.user;
    },
    async register(payload) {
      const data = await this.api("/api/auth/register/", { method: "POST", body: payload, auth: false });
      this.saveSession(data);
      return data.user;
    },
    async logout() {
      const refresh = store.get(KEYS.refresh);
      try { if (refresh) await this.api("/api/auth/logout/", { method: "POST", body: { refresh } }); } catch { /* already invalid */ }
      this.clearSession();
    },
    async reloadUser() {
      const user = await this.api("/api/auth/me/");
      store.set(KEYS.user, JSON.stringify(user));
      this.renderNav();
      return user;
    },

    // DRF errors: {"detail": "..."} for 401/403/404/409, {"field": ["message"]} for validation.
    errorMessage(data, status) {
      if (typeof data.detail === "string") return data.detail;
      const field = Object.keys(data).find((k) => Array.isArray(data[k]) && data[k].length);
      if (field) return field === "non_field_errors" ? data[field][0] : `${this.label(field)}: ${data[field][0]}`;
      return status === 0 ? "Network error" : `HTTP ${status}`;
    },
    label(field) { return field.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase()); },

    // Show field errors under the inputs of a form (inputs are matched by name).
    showFieldErrors(form, data) {
      form.querySelectorAll(".field").forEach((f) => { f.classList.remove("invalid"); const e = f.querySelector(".error"); if (e) e.remove(); });
      let shown = false;
      for (const [field, messages] of Object.entries(data || {})) {
        const input = form.querySelector(`[name="${field}"]`);
        if (!input || !Array.isArray(messages)) continue;
        const wrap = input.closest(".field");
        if (!wrap) continue;
        wrap.classList.add("invalid");
        const err = document.createElement("div"); err.className = "error"; err.textContent = messages[0];
        wrap.appendChild(err); shown = true;
      }
      return shown;
    },

    // --------------------------------------------------------------- helpers
    requireAuth() {
      if (this.isAuthed()) return true;
      location.href = `/login/?next=${encodeURIComponent(location.pathname + location.search)}`;
      return false;
    },
    nextUrl() { const n = new URLSearchParams(location.search).get("next"); return n && n.startsWith("/") ? n : "/"; },
    initials(user) {
      const name = (user.display_name || user.username || "?").trim();
      const parts = name.split(/\s+/);
      return (parts.length > 1 ? parts[0][0] + parts[1][0] : name.slice(0, 2)).toUpperCase();
    },
    fmtTime(iso) { return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); },
    fmtDate(iso) { return new Date(iso).toLocaleDateString([], { year: "numeric", month: "short", day: "numeric" }); },
    fmtDateTime(iso) { return `${this.fmtDate(iso)} ${this.fmtTime(iso)}`; },
    el(tag, attrs = {}, ...children) {
      const node = document.createElement(tag);
      for (const [k, v] of Object.entries(attrs)) {
        if (k === "class") node.className = v;
        else if (k === "html") node.innerHTML = v;
        else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
        else if (v !== null && v !== undefined && v !== false) node.setAttribute(k, v === true ? "" : v);
      }
      for (const child of children.flat()) {
        if (child === null || child === undefined || child === false) continue;
        node.append(child.nodeType ? child : document.createTextNode(String(child)));
      }
      return node;
    },
    rolePill(role) { return this.el("span", { class: `pill role-${role}` }, role); },
    toast(message, type = "") {
      let box = document.querySelector(".toasts");
      if (!box) { box = this.el("div", { class: "toasts" }); document.body.appendChild(box); }
      const t = this.el("div", { class: `toast ${type}` }, message);
      box.appendChild(t);
      setTimeout(() => t.remove(), type === "error" ? 6000 : 3500);
    },
    setStatus(message, isError = false) {
      const el = document.getElementById("status");
      if (!el) return;
      el.textContent = message;
      el.classList.toggle("error", isError);
    },
    async confirm(message) { return window.confirm(message); },

    // ----------------------------------------------------------------- theme
    applyTheme() {
      const saved = store.get(KEYS.theme);
      if (saved) document.documentElement.setAttribute("data-theme", saved);
    },
    toggleTheme() {
      const dark = matchMedia("(prefers-color-scheme: dark)").matches;
      const current = document.documentElement.getAttribute("data-theme") || (dark ? "dark" : "light");
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      store.set(KEYS.theme, next);
    },

    // ------------------------------------------------------------------- nav
    renderNav() {
      const area = document.getElementById("auth-area");
      if (!area) return;
      area.textContent = "";
      const user = this.user();
      if (!user) {
        area.append(
          this.el("a", { class: "btn ghost", href: `/login/?next=${encodeURIComponent(location.pathname)}` }, "Sign in"),
          this.el("a", { class: "btn primary", href: "/register/" }, "Create account"),
        );
        return;
      }
      const menu = this.el("div", { class: "menu" });
      const button = this.el("button", { class: "ghost", type: "button", "aria-haspopup": "true" },
        this.el("span", { class: "avatar" }, this.initials(user)),
        this.el("span", { class: "name-label" }, user.display_name),
      );
      const dropdown = this.el("div", { class: "dropdown" },
        this.el("div", { class: "who" }, this.el("strong", {}, user.display_name), this.el("span", { class: "muted small" }, `@${user.username} · `), this.rolePill(user.role)),
        this.el("a", { href: "/me/" }, "Personal cabinet"),
        this.canCreateLectures() ? this.el("a", { href: "/#new" }, "Start a lecture") : null,
        user.role === "admin" ? this.el("a", { href: "/users/" }, "Users") : null,
        this.el("a", { href: "/docs/" }, "API docs"),
        this.el("button", { type: "button", onclick: async () => { await this.logout(); this.toast("Signed out"); if (location.pathname.startsWith("/me") || location.pathname.startsWith("/users")) location.href = "/"; } }, "Sign out"),
      );
      button.addEventListener("click", (e) => { e.stopPropagation(); menu.classList.toggle("open"); });
      document.addEventListener("click", () => menu.classList.remove("open"));
      menu.append(button, dropdown);
      area.append(menu);
    },

    // ------------------------------------------------------------- questions
    // Build the question list. opts.mode: "audience" | "screen"; opts.onChange re-renders after an action.
    renderQuestions(container, questions, opts = {}) {
      const { mode = "audience", onChange = () => {} } = opts;
      container.textContent = "";
      if (!questions.length) {
        container.append(this.el("div", { class: "empty" },
          this.el("div", { class: "big" }, "🙋"),
          mode === "screen" ? "No questions yet — scan the code and ask one." : "No questions yet. Be the first!"));
        return;
      }
      const authed = this.isAuthed();
      for (const q of questions) {
        const card = this.el("article", { class: `q${q.is_answered ? " answered" : ""}${mode === "screen" ? " big" : ""}` });

        const vote = this.el("button", { class: `vote${q.voted ? " on" : ""}`, type: "button" },
          this.el("span", {}, q.votes), this.el("small", {}, mode === "screen" ? "votes" : (q.voted ? "voted" : "me too")));
        if (mode === "audience") {
          vote.title = authed ? (q.voted ? "Remove my vote" : "I have the same question") : "Sign in to vote";
          vote.addEventListener("click", async () => {
            if (!this.requireAuth()) return;
            try { await this.api(`/api/questions/${q.id}/upvote/`, { method: "POST" }); await onChange(); }
            catch (e) { this.toast(e.message, "error"); }
          });
        } else {
          vote.disabled = true;
        }

        const body = this.el("div");
        const text = this.el("p", { class: "text" }, q.text);
        const who = this.el("div", { class: "who" },
          this.el("span", {}, q.author.display_name),
          this.el("span", {}, "·"),
          this.el("span", {}, this.fmtTime(q.created_at)),
          q.lecture_title && mode === "list" ? this.el("a", { href: `/l/${q.lecture_code}/` }, q.lecture_title) : null,
          q.is_answered ? this.el("span", { class: "pill answered" }, "answered") : null,
        );
        body.append(text, who);

        const tools = this.el("div", { class: "tools" });
        if (q.can_answer) {
          tools.append(this.el("button", { class: "sm", type: "button", onclick: async () => {
            try { await this.api(`/api/questions/${q.id}/answered/`, { method: "POST" }); await onChange(); }
            catch (e) { this.toast(e.message, "error"); }
          } }, q.is_answered ? "Reopen" : "Mark answered"));
        }
        if (q.can_edit && mode !== "screen") {
          tools.append(this.el("button", { class: "sm ghost", type: "button", onclick: () => {
            if (card.querySelector("textarea.edit")) return;
            const area = this.el("textarea", { class: "edit", maxlength: "500" }); area.value = q.text;
            const save = this.el("button", { class: "sm primary", type: "button", onclick: async () => {
              try { await this.api(`/api/questions/${q.id}/`, { method: "PATCH", body: { text: area.value } }); this.toast("Question updated", "ok"); await onChange(); }
              catch (e) { this.toast(e.message, "error"); }
            } }, "Save");
            const cancel = this.el("button", { class: "sm ghost", type: "button", onclick: () => onChange() }, "Cancel");
            text.replaceWith(area); tools.replaceChildren(save, cancel); area.focus();
          } }, "Edit"));
        }
        if (q.can_edit) {
          tools.append(this.el("button", { class: "sm danger ghost", type: "button", onclick: async () => {
            if (!(await this.confirm("Delete this question?"))) return;
            try { await this.api(`/api/questions/${q.id}/`, { method: "DELETE" }); this.toast("Question deleted"); await onChange(); }
            catch (e) { this.toast(e.message, "error"); }
          } }, "Delete"));
        }
        if (tools.childElementCount) body.append(tools);

        card.append(vote, body);
        container.append(card);
      }
    },

    // Poll the API for a lecture and hand the payload to the page. Returns the refresh function.
    startPolling(code, onData) {
      const refresh = async () => {
        try {
          const data = await this.api(`/api/lectures/${code}/`);
          onData(data);
          this.setStatus(`Updated ${new Date().toLocaleTimeString()} · refreshes every ${this.refreshMs / 1000}s`);
        } catch (e) {
          this.setStatus(`Cannot reach the API: ${e.message}`, true);
        }
      };
      refresh();
      setInterval(refresh, this.refreshMs);
      this.refresh = refresh;
      return refresh;
    },
  };

  RH.applyTheme();
  document.addEventListener("DOMContentLoaded", () => {
    RH.renderNav();
    const toggle = document.getElementById("theme-toggle");
    if (toggle) toggle.addEventListener("click", () => RH.toggleTheme());
  });
  return RH;
})();
