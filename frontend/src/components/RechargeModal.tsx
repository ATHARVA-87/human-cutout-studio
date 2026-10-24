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
      <div className="panel modal">
        <h2 id="recharge-title">You're out of credits</h2>
        <p className="soft">
          This needs {cost} {cost === 1 ? "credit" : "credits"} and you have {credits}. Recharge to get 30 free demo credits, then try again.
        </p>
        <div className="confirm-actions">
          <button className="button primary" onClick={onRecharge} disabled={busy} autoFocus>
            Recharge 30 credits
          </button>
          <button className="button quiet" onClick={onClose} disabled={busy}>
            Not now
          </button>
        </div>
      </div>
    </div>
  );
}
