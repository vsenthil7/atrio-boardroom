import { NavLink, useNavigate } from "react-router-dom";
import { useAuthStore } from "@/store/auth";

export function Masthead(): JSX.Element {
  const { user, signOut } = useAuthStore();
  const navigate = useNavigate();

  return (
    <header className="border-b-2 border-ink">
      <div className="max-w-7xl mx-auto px-6 py-4 flex items-end justify-between">
        <NavLink to="/" className="block">
          <div className="byline">
            Vol. I · {new Date().toLocaleDateString("en-GB", {
              year: "numeric",
              month: "long",
              day: "numeric",
            })}
          </div>
          <h1 className="font-display text-3xl font-bold leading-none tracking-tight">
            ATRIO Boardroom
          </h1>
        </NavLink>
        <nav className="flex items-center gap-6 pb-1">
          <NavLink
            to="/"
            end
            className={({ isActive }) => (isActive ? "nav-link nav-link-active" : "nav-link")}
          >
            Sessions
          </NavLink>
          <NavLink
            to="/treasury"
            className={({ isActive }) => (isActive ? "nav-link nav-link-active" : "nav-link")}
          >
            Treasury
          </NavLink>
          <NavLink
            to="/audit"
            className={({ isActive }) => (isActive ? "nav-link nav-link-active" : "nav-link")}
          >
            Audit
          </NavLink>
          <NavLink
            to="/settings"
            className={({ isActive }) => (isActive ? "nav-link nav-link-active" : "nav-link")}
          >
            Settings
          </NavLink>
          {user && (
            <div className="flex items-center gap-3 pl-6 border-l border-rule">
              <span className="font-ui text-sm text-sub" data-testid="user-email">
                {user.email}
              </span>
              <button
                onClick={() => {
                  signOut();
                  navigate("/signin");
                }}
                className="nav-link"
                data-testid="signout"
              >
                Sign out
              </button>
            </div>
          )}
        </nav>
      </div>
    </header>
  );
}
