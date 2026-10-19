import type { Account } from "../types";

interface HeaderProps {
  user?: Account;
  dark: boolean;
  onToggleTheme: () => void;
  onRecharge?: () => void;
  onLogout?: () => void;
}

export function Header({ user, dark, onToggleTheme, onRecharge, onLogout }: HeaderProps) {
  return (
    <header>
      <span className="brand">
        human<span>cutout</span>
      </span>
      <div className="top-actions">
        {user && <strong className="credits">{user.credits} credits</strong>}
        {user && (
          <button className="plain" onClick={onRecharge}>
            Recharge
          </button>
        )}
        <button className="theme" onClick={onToggleTheme} aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}>
          {dark ? "☀" : "☾"}
        </button>
        {user && (
          <button className="plain" onClick={onLogout}>
            Log out
          </button>
        )}
      </div>
    </header>
  );
}
