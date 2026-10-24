import { useLayoutEffect, useRef, useState } from "react";
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
  // One underline that SLIDES to the active link (instead of each link drawing its own border,
  // which made it jump). We measure the active link and move the underline there.
  const navRef = useRef<HTMLElement>(null);
  const [underline, setUnderline] = useState<{ left: number; width: number }>();
  useLayoutEffect(() => {
    const measure = () => {
      const active = navRef.current?.querySelector<HTMLElement>('[aria-current="page"]');
      setUnderline(active ? { left: active.offsetLeft, width: active.offsetWidth } : undefined);
    };
    measure();
    window.addEventListener("resize", measure);
    document.fonts?.ready.then(measure); // re-measure once the web font has loaded (widths change)
    return () => window.removeEventListener("resize", measure);
  }, [route, user]);

  return (
    <header className="site-header">
      <div className="shell">
        <a className="brand" href={href("create")} aria-label="Human Cutout, home">
          human<b>cutout</b>
        </a>
        {user && (
          <nav className="nav" aria-label="Main" ref={navRef}>
            <a href={href("create")} aria-current={route === "create" ? "page" : undefined}>
              Create
            </a>
            <a href={href("history")} aria-current={route === "history" ? "page" : undefined}>
              History
            </a>
            <span
              className="nav-underline"
              aria-hidden="true"
              style={underline ? { width: underline.width, transform: `translateX(${underline.left}px)`, opacity: 1 } : { opacity: 0 }}
            />
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
