/*
 * Routes of the app. Public pages are plain <Route>s; protected pages sit under a
 * <Route element={<RequireAuth />}> — RequireAuth renders them only for a signed-in
 * user and sends everyone else to /login/?next=... (see auth/RequireAuth.jsx).
 */

import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import RequireAuth from "./auth/RequireAuth";
import Layout from "./components/Layout";
import { ToastProvider } from "./components/Toasts";
import Home from "./pages/Home";
import Lecture from "./pages/Lecture";
import Login from "./pages/Login";
import Plan from "./pages/Plan";
import Profile from "./pages/Profile";
import Register from "./pages/Register";
import Screen from "./pages/Screen";
import Users from "./pages/Users";

function NotFound() {
  return <main><div className="card empty"><div className="big">🤷</div>Page not found.</div></main>;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <ToastProvider>
          <Routes>
            <Route element={<Layout />}>
              {/* public */}
              <Route path="/" element={<Home />} />
              <Route path="/login/" element={<Login />} />
              <Route path="/register/" element={<Register />} />
              <Route path="/l/:code/" element={<Lecture />} />
              <Route path="/l/:code/screen/" element={<Screen />} />

              {/* signed-in users only */}
              <Route element={<RequireAuth />}>
                <Route path="/me/" element={<Profile />} />
                <Route path="/l/:code/plan/" element={<Plan />} />
              </Route>

              {/* admins only */}
              <Route element={<RequireAuth roles={["admin"]} />}>
                <Route path="/users/" element={<Users />} />
              </Route>

              <Route path="*" element={<NotFound />} />
            </Route>
          </Routes>
        </ToastProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
