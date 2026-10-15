import type { Prediction } from "../types";
import { api } from "../api/client";

export function PredictionResult({ prediction }: { prediction: Prediction }) {
  const assets = [
    ["Original", prediction.original_url],
    ["Person mask", prediction.mask_url],
    ["Overlay", prediction.overlay_url],
  ] as const;
  return (
    <section className="result-card">
      <div className="result-heading">
        <div><p className="eyebrow">Result</p><h2>{prediction.original_filename}</h2></div>
        <span className="metric">{(prediction.foreground_fraction * 100).toFixed(1)}% foreground</span>
      </div>
      <div className="result-grid">
        {assets.map(([label, url]) => <figure key={label}><img src={api.assetUrl(url)} alt={label} /><figcaption>{label}</figcaption></figure>)}
      </div>
      <p className="muted result-meta">{prediction.source_width} × {prediction.source_height} · {prediction.model_version}</p>
      <div className="download-row">
        <a className="download" href={api.assetUrl(prediction.mask_url)} download="person-mask.png">Download mask</a>
        {prediction.cutout_url && <a className="download" href={api.assetUrl(prediction.cutout_url)} download="person-cutout.png">Download cutout</a>}
        <a className="download" href={api.assetUrl(prediction.overlay_url)} download="person-overlay.png">Download overlay</a>
      </div>
    </section>
  );
}
