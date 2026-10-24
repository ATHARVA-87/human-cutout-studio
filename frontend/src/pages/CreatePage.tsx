import { useState } from "react";
import { api } from "../api/client";
import { Composer } from "../components/Composer";
import { ImagePicker } from "../components/ImagePicker";
import { PredictionResult } from "../components/PredictionResult";
import { type Account, COMPOSE_COST, type Composition, type Prediction, SEGMENT_COST } from "../types";

type Mode = "segment" | "compose";

interface CreatePageProps {
  user: Account;
  busy: boolean;
  setBusy: (busy: boolean) => void;
  onCredits: (credits: number) => void;
  onNeedCredits: (cost: number) => void; // opens the recharge dialog
  onApiError: (caught: unknown, cost: number) => string | undefined; // returns a message to show, if any
}

/** The main page: choose an operation, upload images, see the result. */
export function CreatePage({ user, busy, setBusy, onCredits, onNeedCredits, onApiError }: CreatePageProps) {
  const [mode, setMode] = useState<Mode>("segment");
  const [person, setPerson] = useState<File>();
  const [background, setBackground] = useState<File>();
  const [result, setResult] = useState<Prediction>();
  const [composition, setComposition] = useState<Composition>();
  const [error, setError] = useState<string>();

  const cost = mode === "segment" ? SEGMENT_COST : COMPOSE_COST;

  const run = async () => {
    if (!person || (mode === "compose" && !background)) return;
    if (user.credits < cost) return onNeedCredits(cost); // do not start a job we cannot pay for
    setBusy(true);
    setError(undefined);
    try {
      if (mode === "segment") {
        const prediction = await api.segment(person);
        setResult(prediction);
        setComposition(undefined);
        if (prediction.credits !== null) onCredits(prediction.credits);
      } else {
        const created = await api.compose(person, background!);
        setComposition(created);
        setResult(undefined);
        if (created.credits !== null) onCredits(created.credits);
      }
    } catch (caught) {
      setError(onApiError(caught, cost));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
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
    </>
  );
}
