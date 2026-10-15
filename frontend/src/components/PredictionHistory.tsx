import type { Prediction } from "../types";
import { api } from "../api/client";

interface PredictionHistoryProps {
  items: Prediction[];
  selectedId?: string;
  onSelect: (prediction: Prediction) => void;
}

export function PredictionHistory({ items, selectedId, onSelect }: PredictionHistoryProps) {
  return (
    <aside className="history-panel">
      <div><p className="eyebrow">Recent work</p><h2>History</h2></div>
      {items.length === 0 ? <p className="muted">Your completed cutouts will appear here.</p> : (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <button className={selectedId === item.id ? "history-item active" : "history-item"} onClick={() => onSelect(item)}>
                <img src={api.assetUrl(item.overlay_url)} alt="" />
                <span><strong>{item.original_filename}</strong><small>{new Date(item.created_at).toLocaleString()}</small></span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
