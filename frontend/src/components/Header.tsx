import { type Route, href } from "../router";
import { type Account, COMPOSE_COST } from "../types";

interface HeaderProps {
  user?: Account;
  route: Route;
  dark: boolean;
  busy?: boolean; // a job is running: block actions that would interfere
  onToggleTheme: () => void;
  onRecharge?: () => void;
  onLogout?: () => void;
}

export function Header({ user, route, dark, busy = false, onToggleTheme, onRecharge, onLogout }: HeaderProps) {
  return (
    <header className="site-header">
      <div className="shell">
        <a className="brand" href={href("create")} aria-label="Human Cutout, home">
          human<b>cutout</b>
        </a>
        {user && (
          <nav className="nav" aria-label="Main">
            <a href={href("create")} aria-current={route === "create" ? "page" : undefined}>
              Create
            </a>
            <a href={href("history")} aria-current={route === "history" ? "page" : undefined}>
              History
            </a>
          </nav>
        )}
        <div className="account">
          {user && (
            <span className={user.credits < COMPOSE_COST ? "credits low" : "credits"} aria-live="polite">
              {user.credits} {user.credits === 1 ? "credit" : "credits"}
            </span>
          )}
          {user && (
            <button className="button secondary" onClick={onRecharge} disabled={busy}>
              Recharge
            </button>
          )}
          <button className="button secondary theme" onClick={onToggleTheme} aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}>
            {dark ? "☀" : "☾"}
          </button>
          {user && (
            <button className="button quiet" onClick={onLogout} disabled={busy}>
              Log out
            </button>
          )}
        </div>
      </div>
    </header>
  );
}
