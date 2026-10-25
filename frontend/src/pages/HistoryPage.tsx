import { type FormEvent, useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import { Composer } from "../components/Composer";
import { PasswordInput } from "../components/PasswordInput";
import { PredictionResult } from "../components/PredictionResult";
import { href } from "../router";
import type { Composition, Page, Prediction } from "../types";

type Tab = "cutouts" | "compositions";
type Item = Prediction | Composition;

interface HistoryPageProps {
  retentionDays: number;
  isGuest: boolean;
  onApiError: (caught: unknown) => string | undefined;
  onAccountDeleted: () => void;
}

function daysLeft(expiresAt: string): number {
  return Math.max(0, Math.ceil((new Date(expiresAt).getTime() - Date.now()) / 86_400_000));
}

function deletionText(expiresAt: string): string {
  const days = daysLeft(expiresAt);
  if (days <= 0) return "Deleted today";
  return days === 1 ? "Deleted tomorrow" : `Deleted in ${days} days`;
}

/** "Today", "Yesterday", or a date: the heading for each group of items. */
function dayLabel(createdAt: string): string {
  const day = new Date(createdAt);
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (day.toDateString() === today.toDateString()) return "Today";
  if (day.toDateString() === yesterday.toDateString()) return "Yesterday";
  return day.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

function groupByDay<T extends Item>(items: T[]): [string, T[]][] {
  const groups = new Map<string, T[]>();
  for (const item of items) {
    const label = dayLabel(item.created_at);
    groups.set(label, [...(groups.get(label) ?? []), item]);
  }
  return [...groups.entries()];
}

/** Thumbnail that shows a placeholder if the file is gone (deleted, or the free server restarted). */
function Thumb({ src, checkerboard = false }: { src: string; checkerboard?: boolean }) {
  const [failed, setFailed] = useState(false);
  if (failed) return <div className="thumb missing">This image is no longer on the server</div>;
  return <img className={checkerboard ? "thumb checkerboard" : "thumb"} src={src} alt="" loading="lazy" onError={() => setFailed(true)} />;
}

/** Past uploads and results of the signed-in user, newest first, plus account deletion. */
export function HistoryPage({ retentionDays, isGuest, onApiError, onAccountDeleted }: HistoryPageProps) {
  const [tab, setTab] = useState<Tab>("cutouts");
  const [predictions, setPredictions] = useState<Page<Prediction>>({ items: [], total: 0 });
  const [compositions, setCompositions] = useState<Page<Composition>>({ items: [], total: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string>();
  const [openId, setOpenId] = useState<string>();
  const openRef = useRef<HTMLElement>(null);

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

  // Bring an opened item into view.
  useEffect(() => {
    if (openId) openRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [openId]);

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
    if (!window.confirm("Delete this item and its images? This can't be undone.")) return;
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

  const switchTab = (next: Tab) => {
    setTab(next);
    setOpenId(undefined);
  };

  const page: Page<Item> = tab === "cutouts" ? predictions : compositions;
  const openPrediction = predictions.items.find((item) => item.id === openId);
  const openComposition = compositions.items.find((item) => item.id === openId);

  return (
    <>
      <section className="page-head">
        <h1 className="page-title">History</h1>
        <p>Everything you made in the last {retentionDays} days. After that it's deleted automatically, so download what you want to keep.</p>
      </section>

      <div className="tabs" role="tablist" aria-label="Kind of result">
        <button role="tab" aria-selected={tab === "cutouts"} onClick={() => switchTab("cutouts")}>
          Cutouts<span className="count">{predictions.total}</span>
        </button>
        <button role="tab" aria-selected={tab === "compositions"} onClick={() => switchTab("compositions")}>
          Placed on photos<span className="count">{compositions.total}</span>
        </button>
      </div>

      {error && (
        <p className="notice" role="alert">
          {error}
        </p>
      )}

      {(openPrediction || openComposition) && (
        <section className="mat history-open" ref={openRef} aria-label="Opened item">
          {tab === "cutouts" && openPrediction && <PredictionResult prediction={openPrediction} />}
          {tab === "compositions" && openComposition && (
            <Composer
              item={openComposition}
              onSaved={(placement) =>
                setCompositions((current) => ({
                  ...current,
                  items: current.items.map((item) => (item.id === openComposition.id ? { ...item, placement } : item)),
                }))
              }
            />
          )}
        </section>
      )}

      {loading ? (
        <p className="soft">Loading your history…</p>
      ) : page.items.length === 0 ? (
        <div className="empty-state">
          <strong>{tab === "cutouts" ? "No cutouts yet" : "Nothing placed on a photo yet"}</strong>
          <p className="soft">Results you make appear here for {retentionDays} days.</p>
          <a className="button primary" href={href("create")}>
            Make one now
          </a>
        </div>
      ) : (
        groupByDay(page.items).map(([label, items]) => (
          <section className="day-group" key={label}>
            <h2>{label}</h2>
            <ul className="contact-sheet">
              {items.map((item) => {
                const isCutout = tab === "cutouts";
                const title = isCutout ? (item as Prediction).original_filename : "Person placed on a photo";
                const open = openId === item.id;
                return (
                  <li key={item.id} className={open ? "frame open" : "frame"}>
                    <Thumb src={isCutout ? (item as Prediction).overlay_url : item.cutout_url} checkerboard={!isCutout} />
                    <strong title={title}>{title}</strong>
                    <span className="small soft">
                      Made at {new Date(item.created_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}. {deletionText(item.expires_at)}.
                    </span>
                    <div className="frame-actions">
                      <button className="button quiet" onClick={() => setOpenId(open ? undefined : item.id)} aria-expanded={open}>
                        {open ? "Close" : isCutout ? "Open" : "Edit again"}
                      </button>
                      <button className="button quiet" onClick={() => void remove(item.id)}>
                        Delete
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}
      {page.items.length < page.total && (
        <button className="button secondary" onClick={() => void loadMore()}>
          Show older items
        </button>
      )}

      <DeleteAccount isGuest={isGuest} onApiError={onApiError} onDeleted={onAccountDeleted} />
    </>
  );
}

/** Permanently delete the account after re-entering the password. */
interface DeleteAccountProps {
  isGuest: boolean;
  onApiError: (caught: unknown) => string | undefined;
  onDeleted: () => void;
}

function DeleteAccount({ isGuest, onApiError, onDeleted }: DeleteAccountProps) {
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!isGuest && !password) return setError("Enter your password to confirm it's you.");
    setBusy(true);
    try {
      await api.deleteAccount(isGuest ? undefined : password);
      onDeleted();
    } catch (caught) {
      setError(onApiError(caught));
      setBusy(false);
    }
  };

  return (
    <section className="danger-zone" aria-labelledby="delete-account">
      <h2 id="delete-account">{isGuest ? "Delete this guest session" : "Delete your account"}</h2>
      <p className="soft">
        This removes your account, credits and everything you made, right away. It can't be undone. The{" "}
        <a href={href("privacy")}>privacy page</a> explains what is kept about you.
      </p>
      {!open ? (
        <button className="button destructive" onClick={() => setOpen(true)}>
          {isGuest ? "Delete guest session" : "Delete my account"}
        </button>
      ) : (
        <form className="confirm-form" onSubmit={submit}>
          {!isGuest && (
            <>
              <label htmlFor="confirm-password" className="small">
                Enter your password to confirm
              </label>
              <PasswordInput id="confirm-password" value={password} onChange={setPassword} />
            </>
          )}
          <div className="confirm-actions">
            <button className="button destructive" type="submit" disabled={busy}>
              Delete everything permanently
            </button>
            <button className="button quiet" type="button" disabled={busy} onClick={() => setOpen(false)}>
              Keep my account
            </button>
          </div>
          {error && (
            <p className="notice" role="alert">
              {error}
            </p>
          )}
        </form>
      )}
    </section>
  );
}
