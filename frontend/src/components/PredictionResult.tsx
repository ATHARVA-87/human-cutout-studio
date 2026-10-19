import type { Prediction } from "../types";

export function PredictionResult({ prediction }: { prediction: Prediction }) {
  const images = [
    ["Original", prediction.original_url],
    ["Overlay", prediction.overlay_url],
    ["Person mask", prediction.mask_url],
    ["Cutout", prediction.cutout_url],
  ] as const;
  return (
    <section className="result-card">
      <div className="result-heading">
        <div>
          <p className="eyebrow">Result</p>
          <h2>{prediction.original_filename}</h2>
        </div>
        <span className="metric">{(prediction.foreground_fraction * 100).toFixed(1)}% person</span>
      </div>
      <div className="result-grid">
        {images.map(([label, url]) => (
          <figure key={label}>
            <img src={url} alt={label} className={label === "Cutout" ? "checkerboard" : undefined} />
            <figcaption>{label}</figcaption>
          </figure>
        ))}
      </div>
      <p className="muted result-meta">
        {prediction.source_width} × {prediction.source_height} · {prediction.model_version}
      </p>
      <div className="download-row">
        <a className="primary" href={prediction.cutout_url} download="person-cutout.png">
          Download cutout
        </a>
        <a className="primary" href={prediction.mask_url} download="person-mask.png">
          Download mask
        </a>
        <a className="primary" href={prediction.overlay_url} download="person-overlay.png">
          Download overlay
        </a>
      </div>
    </section>
  );
}
