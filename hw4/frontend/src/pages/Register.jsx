/* Create account: POST /api/auth/register/ signs the new user in right away (tokens in the response). */

import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import { useToast } from "../components/Toasts";
import { useTitle } from "../hooks";
import { fieldErrors } from "../utils";
import { useNextUrl } from "./Login";

const FIELDS = ["username", "first_name", "last_name", "email", "password", "role"];

function Field({ name, label, help, errors, children }) {
  return (
    <div className={`field${errors[name] ? " invalid" : ""}`}>
      <label htmlFor={name}>{label}</label>
      {children}
      {errors[name] ? <div className="error">{errors[name]}</div> : help ? <div className="help">{help}</div> : null}
    </div>
  );
}

export default function Register() {
  useTitle("Create account");
  const { isAuthed, register } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const next = useNextUrl();
  const [form, setForm] = useState({ role: "student", username: "", first_name: "", last_name: "", email: "", password: "" });
  const [errors, setErrors] = useState({});
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (isAuthed) return <Navigate to={next} replace />;

  const set = (name) => (e) => setForm((f) => ({ ...f, [name]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setErrors({}); setBusy(true);
    try {
      const user = await register(form);
      toast(`Welcome, ${user.display_name}!`, "ok");
      navigate(next, { replace: true });
    } catch (err) {
      const fields = fieldErrors(err.data, FIELDS);
      if (Object.keys(fields).length) setErrors(fields); else setError(err.message);
      setBusy(false);
    }
  };

  return (
    <main className="narrow">
      <div className="card pad-lg auth-card">
        <h1>Create account</h1>
        <p className="sub">Students ask and vote; lecturers also run lectures.</p>
        <form onSubmit={submit} noValidate>
          <div className="field">
            <label>I am a</label>
            <div className="segmented">
              {["student", "lecturer"].map((role) => (
                <button key={role} type="button" className={form.role === role ? "active" : ""} onClick={() => setForm((f) => ({ ...f, role }))}>
                  {role[0].toUpperCase() + role.slice(1)}
                </button>
              ))}
            </div>
          </div>
          <Field name="username" label="Username" help="Letters, digits and @/./+/-/_ only." errors={errors}>
            <input type="text" id="username" autoComplete="username" required minLength={3} value={form.username} onChange={set("username")} />
          </Field>
          <div className="row">
            <Field name="first_name" label="First name" errors={errors}>
              <input type="text" id="first_name" autoComplete="given-name" value={form.first_name} onChange={set("first_name")} />
            </Field>
            <Field name="last_name" label="Last name" errors={errors}>
              <input type="text" id="last_name" autoComplete="family-name" value={form.last_name} onChange={set("last_name")} />
            </Field>
          </div>
          <Field name="email" label={<>Email <span className="muted">(optional)</span></>} errors={errors}>
            <input type="email" id="email" autoComplete="email" value={form.email} onChange={set("email")} />
          </Field>
          <Field name="password" label="Password" help="At least 8 characters, not only digits, not too common." errors={errors}>
            <input type="password" id="password" autoComplete="new-password" required minLength={8} value={form.password} onChange={set("password")} />
          </Field>
          {error && <div className="field"><div className="error">{error}</div></div>}
          <button className="primary block" type="submit" disabled={busy}>{busy ? "Creating…" : "Create account"}</button>
        </form>
        <p className="small muted" style={{ textAlign: "center", margin: "14px 0 0" }}>
          Already registered? <Link to={`/login/?next=${encodeURIComponent(next)}`}>Sign in</Link>
        </p>
      </div>
    </main>
  );
}
