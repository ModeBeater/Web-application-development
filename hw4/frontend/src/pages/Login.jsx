/* Sign in: POST /api/auth/login/ -> access + refresh tokens + user; then back to ?next= */

import { useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toasts";
import { useTitle } from "../hooks";

export function useNextUrl() {
  const [params] = useSearchParams();
  const next = params.get("next");
  return next && next.startsWith("/") ? next : "/";
}

export default function Login() {
  useTitle("Sign in");
  const { isAuthed, login } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const next = useNextUrl();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (isAuthed) return <Navigate to={next} replace />;

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const user = await login(username.trim(), password);
      toast(`Signed in as ${user.display_name}`, "ok");
      navigate(next, { replace: true });
    } catch (err) {
      setError(err.status === 401 ? "Wrong username or password." : err.message);
      setBusy(false);
    }
  };

  return (
    <main className="narrow">
      <div className="card pad-lg auth-card">
        <h1>Welcome back</h1>
        <p className="sub">Sign in to ask questions and upvote.</p>
        <form onSubmit={submit} noValidate>
          <div className="field">
            <label htmlFor="username">Username</label>
            <input type="text" id="username" autoComplete="username" required autoFocus value={username} onChange={(e) => setUsername(e.target.value)} />
          </div>
          <div className="field">
            <label htmlFor="password">Password</label>
            <input type="password" id="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </div>
          {error && <div className="field"><div className="error">{error}</div></div>}
          <button className="primary block" type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
        </form>
        <p className="small muted" style={{ textAlign: "center", margin: "14px 0 0" }}>
          No account yet? <Link to={`/register/?next=${encodeURIComponent(next)}`}>Create one</Link>
        </p>
        <div className="demo-box">
          <strong>Demo accounts</strong> (password <code>Demo12345!</code> unless changed in <code>.env</code>):
          <code>admin</code> · <code>lecturer</code> · <code>student</code>
        </div>
      </div>
    </main>
  );
}
