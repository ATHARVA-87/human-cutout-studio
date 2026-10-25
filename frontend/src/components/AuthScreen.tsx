import { type FormEvent, useState } from "react";
import { api } from "../api/client";
import { href } from "../router";
import { type Account, RETENTION_DAYS } from "../types";
import { PasswordInput } from "./PasswordInput";

interface AuthScreenProps {
  notice?: string; // e.g. "your session ended" after being signed out elsewhere
  onSignedIn: (account: Account) => void;
}

/** Checks done in the browser first, so the user gets a clear message without a server round trip. */
function validate(email: string, password: string): string | undefined {
  if (!email.trim()) return "Enter your email address.";
  if (!/^\S+@\S+\.\S+$/.test(email.trim())) return "That email address looks incomplete. Check it and try again.";
  if (!password) return "Enter your password.";
  if (password.length < 8) return "Your password needs at least 8 characters.";
  return undefined;
}

/** The word drawn as a cut-out: outlined letters showing the transparency checkerboard, in a selection box. */
function CutWord({ children }: { children: string }) {
  return (
    <span className="cut">
      {children}
      <svg className="selection" aria-hidden="true">
        <rect x="0" y="0" width="100%" height="100%" />
      </svg>
      {["tl", "tr", "bl", "br"].map((corner) => (
        <span key={corner} className={`handle ${corner}`} aria-hidden="true" />
      ))}
    </span>
  );
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
      setError(caught instanceof Error ? caught.message : "Something went wrong. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  };

  const tryAsGuest = async () => {
    setBusy(true);
    setError(undefined);
    try {
      onSignedIn(await api.guest());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong. Try again in a moment.");
      setBusy(false);
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault(); // pressing Enter signs in
    void submit("login");
  };

  return (
    <section className="intro">
      <div>
        <h1 className="display">
          Cut anyone <CutWord>out</CutWord> of any photo.
        </h1>
        <p className="intro-copy">
          Upload a photo and get the person on a transparent background, then drop them into any other picture. Confirm your email to get 30 free
          credits, or try it without an account.
        </p>
      </div>

      <form className="panel auth-form" onSubmit={onSubmit} noValidate>
        <h2>Sign in or create an account</h2>
        {notice && !error && (
          <p className="notice" role="status">
            {notice}
          </p>
        )}
        <div className="field">
          <span>
            <label htmlFor="email">Email</label>
          </span>
          <input id="email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </div>
        <div className="field">
          <span>
            <label htmlFor="password">Password</label>
          </span>
          <PasswordInput id="password" placeholder="At least 8 characters" value={password} onChange={setPassword} />
          <a className="small forgot-link" href={href("forgot")}>
            Forgot your password?
          </a>
        </div>
        {error && (
          <p className="notice" role="alert">
            {error}
          </p>
        )}
        <div className="form-actions">
          <button className="button primary wide" type="submit" disabled={busy}>
            Sign in
          </button>
          <button className="button secondary wide" type="button" disabled={busy} onClick={() => void submit("register")}>
            Create account
          </button>
        </div>
        <div className="guest-option">
          <p>
            <strong>Just looking?</strong> No email needed: get a temporary guest session with 10 credits. It's deleted when you end it,
            or after 24 hours.
          </p>
          <button className="button quiet" type="button" disabled={busy} onClick={() => void tryAsGuest()}>
            Try it without an account
          </button>
        </div>
        <p className="fine-print">
          Creating an account means you accept how your data is handled, as described on the <a href={href("privacy")}>privacy page</a>.
          Your uploads are deleted after {RETENTION_DAYS} days. Only upload photos you have the right to use.
        </p>
      </form>
    </section>
  );
}
