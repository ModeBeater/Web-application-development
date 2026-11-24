/* Page frame: header with navigation and the user menu, the routed page, footer. */

import { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "./Toasts";
import { initials } from "../utils";

const APP_NAME = "Raise Hand";

export function RolePill({ role }) {
  return <span className={`pill role-${role}`}>{role}</span>;
}

function toggleTheme() {
  const dark = matchMedia("(prefers-color-scheme: dark)").matches;
  const current = document.documentElement.getAttribute("data-theme") || (dark ? "dark" : "light");
  const next = current === "dark" ? "light" : "dark";
  document.documentElement.setAttribute("data-theme", next);
  try { localStorage.setItem("rh.theme", next); } catch { /* ignore */ }
}

function UserMenu() {
  const { user, isAuthed, canCreateLectures, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();

  useEffect(() => {
    if (!open) return undefined;
    const close = () => setOpen(false);
    document.addEventListener("click", close);
    return () => document.removeEventListener("click", close);
  }, [open]);

  if (!isAuthed) {
    const next = encodeURIComponent(location.pathname + location.search);
    return (
      <>
        <Link className="btn ghost" to={`/login/?next=${next}`}>Sign in</Link>
        <Link className="btn primary" to={`/register/?next=${next}`}>Create account</Link>
      </>
    );
  }

  const signOut = async () => {
    await logout();
    toast("Signed out");
    if (location.pathname.startsWith("/me") || location.pathname.startsWith("/users") || location.pathname.endsWith("/plan/")) navigate("/");
  };

  return (
    <div className={`menu${open ? " open" : ""}`}>
      <button className="ghost" type="button" aria-haspopup="true" aria-expanded={open}
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}>
        <span className="avatar">{initials(user)}</span>
        <span className="name-label">{user.display_name}</span>
      </button>
      <div className="dropdown">
        <div className="who">
          <strong>{user.display_name}</strong>
          <span className="muted small">@{user.username} · </span><RolePill role={user.role} />
        </div>
        <Link to="/me/">Personal cabinet</Link>
        {canCreateLectures && <Link to="/me/?tab=lectures">Start a lecture</Link>}
        {user.role === "admin" && <Link to="/users/">Users</Link>}
        <a href="/docs/">API docs</a>
        <button type="button" onClick={signOut}>Sign out</button>
      </div>
    </div>
  );
}

export default function Layout() {
  return (
    <>
      <header className="top">
        <div className="inner">
          <Link className="brand" to="/"><span className="logo">✋</span>{APP_NAME}</Link>
          <nav className="links">
            <NavLink to="/" end>Lectures</NavLink>
            <a href="/docs/">API docs</a>
          </nav>
          <span className="spacer" />
          <button className="icon ghost" type="button" title="Toggle light / dark theme" aria-label="Toggle theme" onClick={toggleTheme}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></svg>
          </button>
          <div className="auth-area"><UserMenu /></div>
        </div>
      </header>

      <Outlet />

      <footer>
        <div className="inner">
          <span>{APP_NAME} · live questions for lectures · React frontend + Django REST API</span>
          <a href="/docs/">API docs</a>
          <a href="/api/">API root</a>
          <a href="/health/">health</a>
        </div>
      </footer>
    </>
  );
}
