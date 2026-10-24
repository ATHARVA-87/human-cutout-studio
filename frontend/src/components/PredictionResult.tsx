import type { Prediction } from "../types";

/** A segmentation result, shown on the mat: the cutout first, then how the model saw the photo. */
export function PredictionResult({ prediction }: { prediction: Prediction }) {
  const images = [
    { label: "Cutout on a transparent background", url: prediction.cutout_url, transparent: true },
    { label: "What the model marked as person", url: prediction.overlay_url, transparent: false },
    { label: "Mask (white is person)", url: prediction.mask_url, transparent: false },
    { label: "Your original photo", url: prediction.original_url, transparent: false },
  ];
  const percent = Math.round(prediction.foreground_fraction * 100);
  return (
    <div className="result-card">
      <div className="mat-head">
        <h2>{prediction.original_filename}</h2>
        <p>The person fills about {percent}% of the photo.</p>
      </div>
      <div className="result-grid">
        {images.map(({ label, url, transparent }) => (
          <figure key={label}>
            <img src={url} alt={label} className={transparent ? "checkerboard" : undefined} />
            <figcaption>{label}</figcaption>
          </figure>
        ))}
      </div>
      <div className="download-row">
        <a className="button on-mat" href={prediction.cutout_url} download="person-cutout.png">
          Download cutout
        </a>
        <a className="button on-mat-outline" href={prediction.mask_url} download="person-mask.png">
          Download mask
        </a>
        <a className="button on-mat-outline" href={prediction.overlay_url} download="person-overlay.png">
          Download overlay
        </a>
      </div>
      <p className="result-meta">
        Processed at {prediction.source_width} by {prediction.source_height} pixels with model {prediction.model_version}.
      </p>
    </div>
  );
}
