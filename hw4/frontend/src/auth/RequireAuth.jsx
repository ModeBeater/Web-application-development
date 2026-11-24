/*
 * Route guard. Wrap protected routes in it:
 *
 *   <Route element={<RequireAuth />}>
 *     <Route path="/me/" element={<Profile />} />
 *   </Route>
 *
 * Signed in  -> renders the child route (<Outlet />).
 * Signed out -> <Navigate /> to /login/?next=<where they wanted to go>, so the login
 *               page can send them back afterwards.
 * roles      -> optionally restrict to roles, e.g. <RequireAuth roles={["admin"]} />:
 *               a signed-in user with another role sees a 403 message instead.
 *
 * This is UI-level protection only: the API checks every request itself
 * (permissions.py on the backend) — the frontend just avoids showing pages that
 * would only produce 401/403 responses.
 */

import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext";

export default function RequireAuth({ roles }) {
  const { isAuthed, user } = useAuth();
  const location = useLocation();

  if (!isAuthed) {
    const next = location.pathname + location.search;
    return <Navigate to={`/login/?next=${encodeURIComponent(next)}`} replace />;
  }
  if (roles && !roles.includes(user.role)) {
    return (
      <div className="card empty">
        <div className="big">🔒</div>
        This page is for {roles.join(" / ")} accounts. You are signed in as <strong>{user.role}</strong>.
      </div>
    );
  }
  return <Outlet />;
}
