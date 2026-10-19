interface RechargeModalProps {
  credits: number;
  cost: number;
  busy: boolean;
  onRecharge: () => void;
  onClose: () => void;
}

/** Shown instead of running a job when the balance is too low (or the server answers 402). */
export function RechargeModal({ credits, cost, busy, onRecharge, onClose }: RechargeModalProps) {
  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="recharge-title">
      <div className="modal">
        <h2 id="recharge-title">Out of credits</h2>
        <p className="muted">
          You have {credits} {credits === 1 ? "credit" : "credits"}; this action needs {cost}. Recharge to add 30 free demo credits.
        </p>
        <div className="modal-actions">
          <button className="primary" onClick={onRecharge} disabled={busy}>
            Recharge 30 credits
          </button>
          <button className="plain" onClick={onClose} disabled={busy}>
            Not now
          </button>
        </div>
      </div>
    </div>
  );
}
