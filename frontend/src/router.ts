import { useEffect, useState } from "react";

/**
 * A tiny hash router: the page is chosen by the part of the URL after "#", e.g. /#/history.
 * Changing the hash never reloads the page or hits the server, and the browser's back/forward
 * buttons work. That's all this app needs, so no routing library is used.
 *
 * Email links look like /#/reset?token=...: everything after "#" (including the token) stays in the
 * browser and is never sent to the server in the request, so tokens don't end up in server logs.
 */
export type Route = "create" | "history" | "model" | "privacy" | "forgot" | "reset" | "verify";

const ROUTES: Route[] = ["history", "model", "privacy", "forgot", "reset", "verify"];

function parse(hash: string): Route {
  const path = hash.replace(/^#\//, "").split("?")[0];
  return ROUTES.find((route) => route === path) ?? "create";
}

export function href(route: Route): string {
  return route === "create" ? "#/" : `#/${route}`;
}

/** The ?token=... part of the current hash (from an email link), if any. */
export function hashToken(): string {
  const query = window.location.hash.split("?")[1] ?? "";
  return new URLSearchParams(query).get("token") ?? "";
}

export function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parse(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parse(window.location.hash));
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}
