import { useEffect, useState } from "react";
import { ApiError, api } from "./api/client";
import { AuthScreen } from "./components/AuthScreen";
import { Composer } from "./components/Composer";
import { Header } from "./components/Header";
import { ImagePicker } from "./components/ImagePicker";
import { PredictionResult } from "./components/PredictionResult";
import { RechargeModal } from "./components/RechargeModal";
import { type Account, COMPOSE_COST, type Composition, type Prediction, SEGMENT_COST } from "./types";

type Mode = "segment" | "compose";

function savedTheme(): boolean {
  try {
    return localStorage.getItem("theme") !== "light";
  } catch {
    return true; // storage can be blocked (private mode); default to dark
  }
}

export default function App() {
  const [user, setUser] = useState<Account>();
  const [checkingSession, setCheckingSession] = useState(true);
  const [dark, setDark] = useState(savedTheme);
  const [mode, setMode] = useState<Mode>("segment");
  const [person, setPerson] = useState<File>();
  const [background, setBackground] = useState<File>();
  const [result, setResult] = useState<Prediction>();
  const [composition, setComposition] = useState<Composition>();
  const [error, setError] = useState<string>();
  const [notice, setNotice] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [rechargeOpen, setRechargeOpen] = useState(false);

  const cost = mode === "segment" ? SEGMENT_COST : COMPOSE_COST;

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

  const clearWork = () => {
    setPerson(undefined);
    setBackground(undefined);
    setResult(undefined);
    setComposition(undefined);
    setError(undefined);
    setRechargeOpen(false);
  };

  /** One place that turns server errors into UI behaviour. */
  const handleError = (caught: unknown) => {
    if (caught instanceof ApiError && caught.status === 401) {
      clearWork();
      setUser(undefined);
      setNotice(caught.message); // e.g. signed in on another device
    } else if (caught instanceof ApiError && caught.status === 402) {
      setRechargeOpen(true);
    } else {
      setError(caught instanceof Error ? caught.message : "Something went wrong.");
    }
  };

  const run = async () => {
    if (!user || !person || (mode === "compose" && !background)) return;
    if (user.credits < cost) return setRechargeOpen(true); // do not start a job we cannot pay for
    setBusy(true);
    setError(undefined);
    try {
      if (mode === "segment") {
        const prediction = await api.segment(person);
        setResult(prediction);
        setComposition(undefined);
        if (prediction.credits !== null) setUser({ ...user, credits: prediction.credits });
      } else {
        const created = await api.compose(person, background!);
        setComposition(created);
        setResult(undefined);
        setUser({ ...user, credits: created.credits });
      }
    } catch (caught) {
      handleError(caught);
    } finally {
      setBusy(false);
    }
  };

  const recharge = async () => {
    setBusy(true);
    try {
      setUser(await api.recharge());
      setRechargeOpen(false);
      setError(undefined);
    } catch (caught) {
      setRechargeOpen(false);
      handleError(caught);
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    await api.logout().catch(() => undefined); // log out locally even if the server is unreachable
    clearWork();
    setUser(undefined);
    setNotice("You have been logged out.");
  };

  const header = (
    <Header
      user={user}
      dark={dark}
      onToggleTheme={() => setDark((value) => !value)}
      onRecharge={() => void recharge()} // the server decides whether a recharge is allowed
      onLogout={logout}
    />
  );

  if (checkingSession) return <main>{header}</main>;

  if (!user) {
    return (
      <main className="auth">
        {header}
        <AuthScreen
          notice={notice}
          onSignedIn={(account) => {
            setNotice(undefined);
            setUser(account);
          }}
        />
      </main>
    );
  }

  return (
    <main>
      {header}
      <section className="hero">
        <p className="eyebrow">Welcome back</p>
        <h1>What would you like to create?</h1>
      </section>
      <section className="operations">
        <button className={mode === "segment" ? "operation selected" : "operation"} onClick={() => setMode("segment")}>
          Person segmentation<small>{SEGMENT_COST} credit · mask and cutout</small>
        </button>
        <button className={mode === "compose" ? "operation selected" : "operation"} onClick={() => setMode("compose")}>
          Combine with another image<small>{COMPOSE_COST} credits · position and edit</small>
        </button>
      </section>
      <section className="upload-card">
        <ImagePicker label="Choose person image" file={person} onPick={setPerson} onError={setError} />
        {mode === "compose" && <ImagePicker label="Choose background image" file={background} onPick={setBackground} onError={setError} />}
        <button className="primary" disabled={busy || !person || (mode === "compose" && !background)} onClick={run}>
          {busy ? "Processing…" : `Continue · ${cost} ${cost === 1 ? "credit" : "credits"}`}
        </button>
        {error && <p className="notice">{error}</p>}
      </section>
      {result && <PredictionResult prediction={result} />}
      {composition && <Composer item={composition} />}
      {rechargeOpen && <RechargeModal credits={user.credits} cost={cost} busy={busy} onRecharge={recharge} onClose={() => setRechargeOpen(false)} />}
    </main>
  );
}
