import { useEffect, useState } from "react";
import { ApiError, api } from "./api/client";
import { AuthScreen } from "./components/AuthScreen";
import { Footer } from "./components/Footer";
import { Header } from "./components/Header";
import { RechargeModal } from "./components/RechargeModal";
import { CreatePage } from "./pages/CreatePage";
import { HistoryPage } from "./pages/HistoryPage";
import { PrivacyPage } from "./pages/PrivacyPage";
import { useRoute } from "./router";
import { type Account, COMPOSE_COST } from "./types";

function savedTheme(): boolean {
  try {
    return localStorage.getItem("theme") !== "light";
  } catch {
    return true; // storage can be blocked (private mode); default to dark
  }
}

/** App-wide state (who is signed in, theme, recharge dialog) and which page to show. */
export default function App() {
  const route = useRoute();
  const [user, setUser] = useState<Account>();
  const [checkingSession, setCheckingSession] = useState(true);
  const [dark, setDark] = useState(savedTheme);
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [rechargeCost, setRechargeCost] = useState<number>(); // set = recharge dialog open

  useEffect(() => {
    document.documentElement.dataset.theme = dark ? "dark" : "light";
    try {
      localStorage.setItem("theme", dark ? "dark" : "light");
    } catch {
      /* ignore */
    }
  }, [dark]);

  // On page load, ask the server whether the session cookie is still valid.
  useEffect(() => {
    api
      .me()
      .then(setUser)
      .catch(() => setUser(undefined))
      .finally(() => setCheckingSession(false));
  }, []);

  const signOut = (message: string) => {
    setUser(undefined);
    setRechargeCost(undefined);
    setNotice(message);
  };

  /** One place that turns server errors into UI behaviour. Returns a message for the page to show, if any. */
  const handleApiError = (caught: unknown, cost = COMPOSE_COST): string | undefined => {
    if (caught instanceof ApiError && caught.status === 401) {
      signOut(caught.message); // e.g. signed in on another device
      return undefined;
    }
    if (caught instanceof ApiError && caught.status === 402) {
      api.me().then(setUser).catch(() => undefined); // show the real balance in the dialog
      setRechargeCost(cost);
      return undefined;
    }
    return caught instanceof Error ? caught.message : "Something went wrong.";
  };

  const recharge = async () => {
    setBusy(true);
    try {
      setUser(await api.recharge());
      setRechargeCost(undefined);
    } catch (caught) {
      setRechargeCost(undefined);
      const message = handleApiError(caught);
      if (message) window.alert(message); // e.g. "Recharge is available when you have fewer than 2 credits."
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    await api.logout().catch(() => undefined); // log out locally even if the server is unreachable
    signOut("You have been logged out.");
  };

  const header = (
    <Header
      user={user}
      route={route}
      dark={dark}
      busy={busy}
      onToggleTheme={() => setDark((value) => !value)}
      onRecharge={() => void recharge()} // the server decides whether a recharge is allowed
      onLogout={logout}
    />
  );

  let page;
  if (route === "privacy") {
    page = <PrivacyPage />; // public: readable without an account
  } else if (checkingSession) {
    page = null;
  } else if (!user) {
    page = (
      <AuthScreen
        notice={notice}
        onSignedIn={(account) => {
          setNotice(undefined);
          setUser(account);
        }}
      />
    );
  } else if (route === "history") {
    page = (
      <HistoryPage
        retentionDays={user.retention_days}
        onApiError={handleApiError}
        onAccountDeleted={() => signOut("Your account and all of its data were deleted.")}
      />
    );
  } else {
    page = (
      <CreatePage
        user={user}
        busy={busy}
        setBusy={setBusy}
        onCredits={(credits) => setUser((current) => current && { ...current, credits })}
        onNeedCredits={setRechargeCost}
        onApiError={handleApiError}
      />
    );
  }

  return (
    <>
      <main className={!user && route !== "privacy" ? "auth" : undefined}>
        {header}
        {page}
        {user && rechargeCost !== undefined && (
          <RechargeModal credits={user.credits} cost={rechargeCost} busy={busy} onRecharge={recharge} onClose={() => setRechargeCost(undefined)} />
        )}
      </main>
      <Footer />
    </>
  );
}
