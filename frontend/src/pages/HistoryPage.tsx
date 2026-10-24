import { type FormEvent, useEffect, useState } from "react";
import { api } from "../api/client";
import { Composer } from "../components/Composer";
import { PasswordInput } from "../components/PasswordInput";
import { PredictionResult } from "../components/PredictionResult";
import type { Composition, Page, Prediction } from "../types";

type Tab = "cutouts" | "compositions";

interface HistoryPageProps {
  retentionDays: number;
  onApiError: (caught: unknown) => string | undefined;
  onAccountDeleted: () => void;
}

function daysLeft(expiresAt: string): number {
  return Math.max(0, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 86_400_000));
}

/** Thumbnail that shows a placeholder if the file is gone (deleted, or the free server restarted). */
function Thumb({ src, checkerboard = false }: { src: string; checkerboard?: boolean }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <div className="thumb missing">Image no longer available</div>;
  return <img className={checkerboard ? "thumb checkerboard" : "thumb"} src={src} alt="" loading="lazy" onError={() => setFailed(true)} />;
}

/** Past uploads and results of the signed-in user, newest first, plus "Your data" (delete account). */
export function HistoryPage({ retentionDays, onApiError, onAccountDeleted }: HistoryPageProps) {
  const [tab, setTab] = useState<Tab>("cutouts");
  const [predictions, setPredictions] = useState<Page<Prediction>>({ items: [], total: 0 });
  const [compositions, setCompositions] = useState<Page<Composition>>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [openId, setOpenId] = useState<string>();

  // Load the first page of both lists when the page opens.
  useEffect(() => {
    Promise.all([api.listPredictions(), api.listCompositions()])
      .then(([cutoutPage, compositionPage]) => {
        setPredictions(cutoutPage);
        setCompositions(compositionPage);
      })
      .catch((caught) => setError(onApiError(caught)))
      .finally(() => setLoading(false));
  }, []); // empty list: load once when the page opens

  const loadMore = async () => {
    try {
      if (tab === "cutouts") {
        const next = await api.listPredictions(predictions.items.length);
        setPredictions((current) => ({ items: [...current.items, ...next.items], total: next.total }));
      } else {
        const next = await api.listCompositions(compositions.items.length);
        setCompositions((current) => ({ items: [...current.items, ...next.items], total: next.total }));
      }
    } catch (caught) {
      setError(onApiError(caught));
    }
  };

  const remove = async (id: string) => {
    if (!window.confirm("Delete this item and its images permanently?")) return;
    try {
      if (tab === "cutouts") {
        await api.deletePrediction(id);
        setPredictions((current) => ({ items: current.items.filter((item) => item.id !== id), total: current.total - 1 }));
      } else {
        await api.deleteComposition(id);
        setCompositions((current) => ({ items: current.items.filter((item) => item.id !== id), total: current.total - 1 }));
      }
      if (openId === id) setOpenId(undefined);
    } catch (caught) {
      setError(onApiError(caught));
    }
  };

  const page = tab === "cutouts" ? predictions : compositions;
  const openPrediction = predictions.items.find((item) => item.id === openId);
  const openComposition = compositions.items.find((item) => item.id === openId);

  return (
    <>
      <section className="hero compact">
        <p className="eyebrow">Your work</p>
        <h1>History</h1>
        <p>Uploads and results are kept for {retentionDays} days, then deleted automatically.</p>
      </section>

      <section className="operations" role="tablist">
        <button role="tab" aria-selected={tab === "cutouts"} className={tab === "cutouts" ? "operation selected" : "operation"} onClick={() => setTab("cutouts")}>
          Cutouts<small>{predictions.total} saved</small>
        </button>
        <button
          role="tab"
          aria-selected={tab === "compositions"}
          className={tab === "compositions" ? "operation selected" : "operation"}
          onClick={() => setTab("compositions")}
        >
          Compositions<small>{compositions.total} saved</small>
        </button>
      </section>

      {error && <p className="notice">{error}</p>}
      {loading ? (
        <p className="muted">Loading…</p>
      ) : page.items.length === 0 ? (
        <p className="muted">Nothing here yet. Results you create appear here for {retentionDays} days.</p>
      ) : (
        <ul className="history-grid">
          {tab === "cutouts"
            ? predictions.items.map((item) => (
                <li key={item.id} className={openId === item.id ? "history-card open" : "history-card"}>
                  <Thumb src={item.overlay_url} />
                  <strong title={item.original_filename}>{item.original_filename}</strong>
                  <small>
                    {new Date(item.created_at).toLocaleString()} · deleted in {daysLeft(item.expires_at)} d
                  </small>
                  <div className="card-actions">
                    <button className="plain" onClick={() => setOpenId(openId === item.id ? undefined : item.id)}>
                      {openId === item.id ? "Close" : "Open"}
                    </button>
                    <button className="plain danger" onClick={() => void remove(item.id)}>
                      Delete
                    </button>
                  </div>
                </li>
              ))
            : compositions.items.map((item) => (
                <li key={item.id} className={openId === item.id ? "history-card open" : "history-card"}>
                  <Thumb src={item.cutout_url} checkerboard />
                  <strong>Composition</strong>
                  <small>
                    {new Date(item.created_at).toLocaleString()} · deleted in {daysLeft(item.expires_at)} d
                  </small>
                  <div className="card-actions">
                    <button className="plain" onClick={() => setOpenId(openId === item.id ? undefined : item.id)}>
                      {openId === item.id ? "Close" : "Edit again"}
                    </button>
                    <button className="plain danger" onClick={() => void remove(item.id)}>
                      Delete
                    </button>
                  </div>
                </li>
              ))}
        </ul>
      )}
      {page.items.length < page.total && (
        <button className="plain load-more" onClick={() => void loadMore()}>
          Load more
        </button>
      )}

      {tab === "cutouts" && openPrediction && <PredictionResult prediction={openPrediction} />}
      {tab === "compositions" && openComposition && <Composer item={openComposition} />}

      <DeleteAccount onApiError={onApiError} onDeleted={onAccountDeleted} />
    </>
  );
}

/** "Your data": permanently delete the account after re-entering the password. */
function DeleteAccount({ onApiError, onDeleted }: { onApiError: (caught: unknown) => string | undefined; onDeleted: () => void }) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!password) return setError("Enter your password to confirm.");
    setBusy(true);
    try {
      await api.deleteAccount(password);
      onDeleted();
    } catch (caught) {
      setError(onApiError(caught));
      setBusy(false);
    }
  };

  return (
    <section className="result-card danger-zone">
      <p className="eyebrow">Your data</p>
      <h2>Delete account</h2>
      <p className="muted">
        This permanently deletes your account, credits and every upload and result. It cannot be undone. See the{" "}
        <a href="#/privacy">Privacy Notice</a> for what we store.
      </p>
      {!open ? (
        <button className="plain danger" onClick={() => setOpen(true)}>
          Delete my account…
        </button>
      ) : (
        <form className="confirm-form" onSubmit={submit}>
          <PasswordInput value={password} onChange={setPassword} placeholder="Your password" />
          <div className="modal-actions">
            <button className="primary danger" type="submit" disabled={busy}>
              Permanently delete
            </button>
            <button className="plain" type="button" disabled={busy} onClick={() => setOpen(false)}>
              Cancel
            </button>
          </div>
          {error && <p className="notice">{error}</p>}
        </form>
      )}
    </section>
  );
}
