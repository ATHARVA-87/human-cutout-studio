import { type FormEvent, useState } from "react";
import { api } from "../api/client";
import { PasswordInput } from "../components/PasswordInput";
import { hashToken, href } from "../router";

/** Opened from the reset email (/#/reset?token=...): choose a new password. */
export function ResetPasswordPage({ onReset }: { onReset: () => void }) {
  const [token] = useState(hashToken);
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (password.length < 8) return setError("Your new password needs at least 8 characters.");
    if (password !== repeat) return setError("The two passwords don't match. Type them again.");
    setBusy(true);
    setError(undefined);
    try {
      await api.resetPassword(token, password);
      onReset(); // signed out everywhere: back to the sign-in screen with a message
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Something went wrong. Try again in a moment.");
      setBusy(false);
    }
  };

  if (!token) {
    return (
      <section className="narrow-page">
        <h1 className="page-title">Reset your password</h1>
        <p className="notice" role="alert">
          This link is incomplete. Open the link from the email again, or <a href={href("forgot")}>request a new one</a>.
        </p>
      </section>
    );
  }

  return (
    <section className="narrow-page">
      <h1 className="page-title">Choose a new password</h1>
      <form className="panel auth-form" onSubmit={submit} noValidate>
        <div className="field">
          <span>
            <label htmlFor="new-password">New password</label>
          </span>
          <PasswordInput id="new-password" autoComplete="new-password" placeholder="At least 8 characters" value={password} onChange={setPassword} />
        </div>
        <div className="field">
          <span>
            <label htmlFor="repeat-password">Type it again</label>
          </span>
          <PasswordInput id="repeat-password" autoComplete="new-password" value={repeat} onChange={setRepeat} />
        </div>
        {error && (
          <p className="notice" role="alert">
            {error} {error.includes("expired") && <a href={href("forgot")}>Request a new link</a>}
          </p>
        )}
        <button className="button primary wide" type="submit" disabled={busy}>
          {busy ? "Saving…" : "Save new password"}
        </button>
        <p className="fine-print">After saving, you'll be signed out on all devices and can sign in with the new password.</p>
      </form>
    </section>
  );
}
