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

    // multipart/form-data POST (file uploads); same token handling as api()
    async upload(path, formData, _retry = true) {
      const headers = { Accept: "application/json" };
      const access = store.get(KEYS.access);
      if (access) headers.Authorization = `Bearer ${access}`;
      const res = await fetch(path, { method: "POST", headers, body: formData });
      const data = await res.json().catch(() => ({}));
      if (res.status === 401 && _retry && store.get(KEYS.refresh)) {
        if (await this.refreshTokens()) return this.upload(path, formData, false);
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
    // opts.topics: the lecture's topics (for the topic picker and the chip colours); opts.topicFilter: id | "none" | null
    renderQuestions(container, questions, opts = {}) {
      const { mode = "audience", onChange = () => {}, topics = [], topicFilter = null } = opts;
      container.textContent = "";
      if (topicFilter !== null && topicFilter !== undefined) {
        questions = questions.filter((q) => topicFilter === "none" ? !q.topic_id : q.topic_id === topicFilter);
      }
      if (!questions.length) {
        container.append(this.el("div", { class: "empty" },
          this.el("div", { class: "big" }, "🙋"),
          topicFilter ? "No questions on this topic yet." :
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
          this.topicChip(q, topics),
          q.is_answered ? this.el("span", { class: "pill answered" }, "answered") : null,
        );
        body.append(text, who);
        if (q.answer) {
          body.append(this.el("div", { class: "answer" },
            this.el("div", { class: "answer-label" }, "Answer", this.el("span", { class: "muted" }, ` · ${q.answer.author ? q.answer.author.display_name : "lecturer"}`)),
            this.el("div", { class: "answer-text" }, q.answer.text)));
        }

        const tools = this.el("div", { class: "tools" });
        if (q.can_answer) {
          tools.append(this.el("button", { class: "sm", type: "button", onclick: async () => {
            try { await this.api(`/api/questions/${q.id}/answered/`, { method: "POST" }); await onChange(); }
            catch (e) { this.toast(e.message, "error"); }
          } }, q.is_answered ? "Reopen" : "Mark answered"));
          if (mode !== "screen") {
            tools.append(this.el("button", { class: "sm ghost", type: "button", onclick: () => this.answerEditor(card, q, onChange) },
              q.answer ? "Edit answer" : "Write answer"));
            if (topics.length) tools.append(this.topicPicker(q, topics, onChange));
          }
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

    // ---------------------------------------------------------- topics, answers
    topicIndex(topics, id) { const i = topics.findIndex((t) => t.id === id); return i < 0 ? 0 : i % 8; },
    topicChip(q, topics = []) {
      if (!q.topic_id) return null;
      const auto = q.tag_source === "auto";
      const chip = this.el("span", { class: `pill topic t${this.topicIndex(topics, q.topic_id)}` }, q.topic_title || "topic",
        auto ? this.el("span", { class: "auto", title: `Tagged by the model, confidence ${(q.tag_score || 0).toFixed(2)}` }, "·auto") : null);
      chip.title = auto ? `Topic suggested automatically (score ${(q.tag_score || 0).toFixed(2)})` : "Topic chosen by a person";
      return chip;
    },
    // <select> that re-tags the question (lecturer / admin): PATCH topic_id; "" = no topic
    topicPicker(q, topics, onChange) {
      const select = this.el("select", { class: "sm topic-select", title: "Change the topic" },
        this.el("option", { value: "" }, "— no topic —"),
        ...topics.map((t) => this.el("option", { value: t.id, selected: t.id === q.topic_id }, t.title)));
      select.addEventListener("change", async () => {
        try { await this.api(`/api/questions/${q.id}/`, { method: "PATCH", body: { topic_id: select.value ? Number(select.value) : null } }); await onChange(); }
        catch (e) { this.toast(e.message, "error"); }
      });
      return select;
    },
    answerEditor(card, q, onChange) {
      if (card.querySelector("form.answer-form")) return;
      const area = this.el("textarea", { maxlength: "2000", placeholder: "Your written answer — the audience sees it under the question" });
      area.value = q.answer ? q.answer.text : "";
      const form = this.el("form", { class: "answer-form" }, area, this.el("div", { class: "row" },
        this.el("button", { class: "sm primary fixed", type: "submit" }, q.answer ? "Save answer" : "Publish answer"),
        q.answer ? this.el("button", { class: "sm danger ghost fixed", type: "button", onclick: async () => {
          if (!(await this.confirm("Remove the written answer? The question will be reopened."))) return;
          try { await this.api(`/api/questions/${q.id}/answer/`, { method: "DELETE" }); this.toast("Answer removed"); await onChange(); }
          catch (e) { this.toast(e.message, "error"); }
        } }, "Remove") : null,
        this.el("button", { class: "sm ghost fixed", type: "button", onclick: () => form.remove() }, "Cancel")));
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        try { await this.api(`/api/questions/${q.id}/answer/`, { method: "PUT", body: { text: area.value } }); this.toast("Answer published", "ok"); await onChange(); }
        catch (err) { this.toast(err.message, "error"); }
      });
      card.querySelector(".tools").after(form); area.focus();
    },
    // Chip row "All · topic (n) · No topic (n)"; calls onSelect(id | "none" | null)
    topicFilterBar(container, topics, questions, current, onSelect) {
      container.textContent = "";
      if (!topics.length) { container.classList.add("hidden"); return; }
      container.classList.remove("hidden");
      const count = (id) => questions.filter((q) => id === "none" ? !q.topic_id : q.topic_id === id).length;
      const chip = (label, value, n, extra = "") => {
        const b = this.el("button", { class: `chip${current === value ? " active" : ""} ${extra}`, type: "button" }, label,
          n !== null ? this.el("span", { class: "n" }, n) : null);
        b.addEventListener("click", () => onSelect(current === value ? null : value));
        return b;
      };
      container.append(chip("All", null, questions.length));
      topics.forEach((t, i) => container.append(chip(t.title, t.id, count(t.id), `t${i % 8}`)));
      if (count("none")) container.append(chip("No topic", "none", count("none")));
    },
    debounce(fn, ms = 400) { let timer; return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); }; },
    // Live hints under the question field: similar questions already asked + the topic the model would pick
    async askAssistant(code, text, box, onChange) {
      box.textContent = "";
      if (text.trim().length < 6) { box.classList.add("hidden"); return; }
      try {
        const [similar, suggestion] = await Promise.all([
          this.api(`/api/lectures/${code}/similar/?text=${encodeURIComponent(text)}`, { auth: false }),
          this.api(`/api/lectures/${code}/suggest/?text=${encodeURIComponent(text)}`, { auth: false }),
        ]);
        if (suggestion.topic_title) {
          box.append(this.el("div", { class: "hint-line" }, "Will be filed under ",
            this.el("span", { class: "pill topic" }, suggestion.topic_title),
            this.el("span", { class: "muted small" }, ` (confidence ${suggestion.score.toFixed(2)}) — or pick a topic below`)));
        }
        if (similar.length) {
          box.append(this.el("div", { class: "hint-line" }, this.el("strong", {}, "Already asked?"), " Upvote instead of posting a duplicate:"));
          for (const m of similar) {
            const { question: q } = m;
            box.append(this.el("div", { class: "similar" },
              this.el("button", { class: `vote sm${q.voted ? " on" : ""}`, type: "button", onclick: async () => {
                if (!this.requireAuth()) return;
                try { await this.api(`/api/questions/${q.id}/upvote/`, { method: "POST" }); this.toast(q.voted ? "Vote removed" : "Voted", "ok"); await onChange(); }
                catch (e) { this.toast(e.message, "error"); }
              } }, this.el("span", {}, q.votes), this.el("small", {}, "me too")),
              this.el("span", { class: "sim-text" }, q.text),
              this.el("span", { class: "muted small" }, `${Math.round(m.similarity * 100)}%`)));
          }
        }
        box.classList.toggle("hidden", !box.childElementCount);
      } catch { box.classList.add("hidden"); }
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
