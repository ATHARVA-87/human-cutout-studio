import { useEffect, useState } from "react";

/**
 * A tiny hash router: the page is chosen by the part of the URL after "#", e.g. /#/history.
 * Changing the hash never reloads the page or hits the server, and the browser's back/forward
 * buttons work. That's all this app needs, so no routing library is used.
 */
export type Route = "create" | "history" | "privacy";

function parse(hash: string): Route {
  if (hash === "#/history") return "history";
  if (hash === "#/privacy") return "privacy";
  return "create";
}

export function href(route: Route): string {
  return route === "create" ? "#/" : `#/${route}`;
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
