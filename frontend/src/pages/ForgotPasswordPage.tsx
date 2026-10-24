import { type FormEvent, useState } from "react";
import { api } from "../api/client";
import { href } from "../router";

/** "Forgot your password?": asks for the email and sends a reset link (the answer never reveals if an account exists). */
export function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState<string>();
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) return setError("Enter the email address you signed up with.");
    setBusy(true);
    setError(undefined);
    try {
      setSent((await api.forgotPassword(email.trim())).detail);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong. Try again in a moment.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="narrow-page">
      <h1 className="page-title">Reset your password</h1>
      {sent ? (
        <div className="panel auth-form">
          <p role="status">{sent}</p>
          <p className="soft">The link works for 30 minutes. Check your spam folder if it doesn't arrive in a few minutes.</p>
          <a className="button secondary" href={href("create")}>
            Back to sign in
          </a>
        </div>
      ) : (
        <form className="panel auth-form" onSubmit={submit} noValidate>
          <p className="soft">Enter the email address of your account and we'll send you a link to choose a new password.</p>
          <div className="field">
            <span>
              <label htmlFor="forgot-email">Email</label>
            </span>
            <input id="forgot-email" type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} />
          </div>
          {error && (
            <p className="notice" role="alert">
              {error}
            </p>
          )}
          <div className="form-actions">
            <button className="button primary wide" type="submit" disabled={busy}>
              {busy ? "Sending…" : "Send reset link"}
            </button>
            <a className="button quiet" href={href("create")}>
              Back to sign in
            </a>
          </div>
        </form>
      )}
    </section>
  );
}
