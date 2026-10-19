import { type FormEvent, useState } from "react";
import { api } from "../api/client";
import type { Account } from "../types";

interface AuthScreenProps {
  notice?: string; // e.g. "your session ended" after being signed out elsewhere
  onSignedIn: (account: Account) => void;
}

/** Checks done in the browser first, so the user gets a clear message without a server round trip. */
function validate(email: string, password: string): string | undefined {
  if (!email.trim()) return "Enter your email address.";
  if (!/^\S+@\S+\.\S+$/.test(email.trim())) return "Enter a valid email address.";
  if (!password) return "Enter your password.";
  if (password.length < 8) return "Password must be at least 8 characters.";
  return undefined;
}

export function AuthScreen({ notice, onSignedIn }: AuthScreenProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const submit = async (kind: "login" | "register") => {
    const problem = validate(email, password);
    if (problem) return setError(problem);
    setBusy(true);
    setError(undefined);
    try {
      const account = kind === "login" ? await api.login(email.trim(), password) : await api.register(email.trim(), password);
      onSignedIn(account);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to continue.");
    } finally {
      setBusy(false);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault(); // pressing Enter signs in
    void submit("login");
  };

  return (
    <>
      <section className="hero">
        <p className="eyebrow">U-Net image studio</p>
        <h1>Make every person fit the picture.</h1>
        <p>Create an account to receive 30 free credits.</p>
      </section>
      <form className="auth-card" onSubmit={onSubmit} noValidate>
        {notice && !error && <p className="notice">{notice}</p>}
        <input placeholder="Email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        <input
          placeholder="Password (8+ characters)"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <button className="primary" type="submit" disabled={busy}>
          Sign in
        </button>
        <button className="plain" type="button" disabled={busy} onClick={() => void submit("register")}>
          Create account
        </button>
        {error && <p className="notice">{error}</p>}
      </form>
    </>
  );
}
