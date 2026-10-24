import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { hashToken, href } from "../router";

/** Opened from the verification email (/#/verify?token=...): confirms the address straight away. */
export function VerifyEmailPage({ signedIn, onVerified }: { signedIn: boolean; onVerified: () => void }) {
  const [state, setState] = useState<"working" | "done" | "failed">("working");
  const [error, setError] = useState<string>();
  const started = useRef(false); // React may run effects twice in development; the token works only once

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const token = hashToken();
    if (!token) {
      setError("This link is incomplete. Open the link from the email again.");
      return setState("failed");
    }
    api
      .verifyEmail(token)
      .then(() => {
        setState("done");
        onVerified();
      })
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "Something went wrong.");
        setState("failed");
      });
  }, []); // empty list: run once when the page opens

  return (
    <section className="narrow-page">
      <h1 className="page-title">{state === "done" ? "Email confirmed" : "Confirming your email"}</h1>
      <div className="panel auth-form" role="status">
        {state === "working" && <p>One moment…</p>}
        {state === "done" && (
          <>
            <p>Thanks, your email address is confirmed. You can make cutouts now.</p>
            <a className="button primary" href={href("create")}>
              {signedIn ? "Start creating" : "Sign in"}
            </a>
          </>
        )}
        {state === "failed" && (
          <>
            <p className="notice">{error}</p>
            <p className="soft">
              {signedIn ? "You can send a new link from the Create page." : "Sign in to send yourself a new link."}
            </p>
            <a className="button secondary" href={href("create")}>
              {signedIn ? "Go to Create" : "Sign in"}
            </a>
          </>
        )}
      </div>
    </section>
  );
}
