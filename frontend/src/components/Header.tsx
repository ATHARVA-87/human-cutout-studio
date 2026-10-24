import { type Route, href } from "../router";
import type { Account } from "../types";

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
    <header>
      <a className="brand" href={href("create")}>
        human<span>cutout</span>
      </a>
      {user && (
        <nav className="nav">
          <a href={href("create")} aria-current={route === "create" ? "page" : undefined}>
            Create
          </a>
          <a href={href("history")} aria-current={route === "history" ? "page" : undefined}>
            History
          </a>
        </nav>
      )}
      <div className="top-actions">
        {user && <strong className="credits">{user.credits} credits</strong>}
        {user && (
          <button className="plain" onClick={onRecharge} disabled={busy}>
            Recharge
          </button>
        )}
        <button className="theme" onClick={onToggleTheme} aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}>
          {dark ? "☀" : "☾"}
        </button>
        {user && (
          <button className="plain" onClick={onLogout} disabled={busy}>
            Log out
          </button>
        )}
      </div>
    </header>
  );
}
