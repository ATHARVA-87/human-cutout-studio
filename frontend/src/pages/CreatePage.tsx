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

  const ready = Boolean(person && (mode === "segment" || background));
  const action = mode === "segment" ? "Cut out the person" : "Cut out and place";

  return (
    <>
      <section className="page-head">
        <h1 className="page-title">Make a cutout</h1>
        <p>Pick what you want, add your photo, and the model finds the person. Results show up on the mat.</p>
      </section>

      <div className="workbench">
        <ol className="steps">
          <li className="step">
            <span className="step-number" aria-hidden="true">1</span>
            <h2 id="step-choose">Choose what to make</h2>
            <div className="step-body" role="radiogroup" aria-labelledby="step-choose">
              <label className="choice">
                <input type="radio" name="mode" checked={mode === "segment"} onChange={() => setMode("segment")} />
                <strong>Cut out a person</strong>
                <span>{SEGMENT_COST} credit. You get a mask, an overlay and a transparent cutout.</span>
              </label>
              <label className="choice">
                <input type="radio" name="mode" checked={mode === "compose"} onChange={() => setMode("compose")} />
                <strong>Place a person on another photo</strong>
                <span>{COMPOSE_COST} credits. Then move, resize and mirror them in the editor.</span>
              </label>
            </div>
          </li>
          <li className="step">
            <span className="step-number" aria-hidden="true">2</span>
            <h2>{mode === "segment" ? "Add your photo" : "Add both photos"}</h2>
            <div className="step-body">
              <ImagePicker label="Photo with a person" file={person} onPick={setPerson} onError={setError} />
              {mode === "compose" && <ImagePicker label="New background" file={background} onPick={setBackground} onError={setError} />}
            </div>
          </li>
          <li className="step">
            <span className="step-number" aria-hidden="true">3</span>
            <h2>Cut it out</h2>
            <div className="step-body">
              <button className="button primary wide" disabled={busy || !ready} onClick={run}>
                {busy ? "Cutting…" : `${action} (${cost} ${cost === 1 ? "credit" : "credits"})`}
              </button>
              {!ready && !busy && <p className="small soft">{mode === "segment" ? "Add a photo first." : "Add both photos first."}</p>}
              {error && (
                <p className="notice" role="alert">
                  {error}
                </p>
              )}
            </div>
          </li>
        </ol>

        <section className="mat" aria-live="polite" aria-label="Result">
          {result && <PredictionResult prediction={result} />}
          {composition && <Composer item={composition} onSaved={(placement) => setComposition((current) => current && { ...current, placement })} />}
          {!result && !composition && (
            <div className="mat-empty">
              <strong>{busy ? "Cutting out the person…" : "Your result appears here"}</strong>
              <span>
                {busy
                  ? "This takes a few seconds."
                  : "Start with a photo where the person is clearly visible. Full-body shots work best for placing on a new background."}
              </span>
            </div>
          )}
        </section>
      </div>
    </>
  );
}
