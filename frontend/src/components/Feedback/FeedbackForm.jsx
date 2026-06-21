import { useState } from "react";
import { api } from "../../api/client.js";
import "./FeedbackForm.css";

export default function FeedbackForm({ eventId, onClose, onSubmitted }) {
  const [duration, setDuration] = useState("");
  const [closureNeeded, setClosureNeeded] = useState("");
  const [severity, setSeverity] = useState("");
  const [officers, setOfficers] = useState("");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    setSubmitting(true);
    setErr(null);
    try {
      await api.submitFeedback({
        event_id: eventId,
        actual_duration_mins: duration === "" ? null : Number(duration),
        actual_closure_needed: closureNeeded === "" ? null : closureNeeded === "yes",
        actual_severity: severity === "" ? null : severity,
        officers_deployed: officers === "" ? null : Number(officers),
        notes: notes || null,
      });
      onSubmitted();
    } catch (e2) {
      setErr(e2);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="vy-modal-backdrop" onClick={onClose}>
      <form className="vy-modal" onClick={(e) => e.stopPropagation()} onSubmit={handleSubmit}>
        <div className="vy-modal-header">
          <h3>Log actual outcome</h3>
          <button type="button" className="vy-back" onClick={onClose}>
            ✕
          </button>
        </div>
        <p className="vy-modal-intro">
          This feeds the post-event learning loop — folded back into the next training run via{" "}
          <code className="mono">scripts/retrain_from_feedback.py</code>.
        </p>

        <div className="field-row">
          <div className="field">
            <label>Actual duration (min)</label>
            <input
              type="number"
              min="0"
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              placeholder="e.g. 45"
            />
          </div>
          <div className="field">
            <label>Officers deployed</label>
            <input
              type="number"
              min="0"
              value={officers}
              onChange={(e) => setOfficers(e.target.value)}
              placeholder="e.g. 3"
            />
          </div>
        </div>

        <div className="field-row">
          <div className="field">
            <label>Closure actually needed?</label>
            <select value={closureNeeded} onChange={(e) => setClosureNeeded(e.target.value)}>
              <option value="">Not sure / skip</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </div>
          <div className="field">
            <label>Actual severity</label>
            <select value={severity} onChange={(e) => setSeverity(e.target.value)}>
              <option value="">Skip</option>
              <option value="Low">Low</option>
              <option value="Medium">Medium</option>
              <option value="High">High</option>
            </select>
          </div>
        </div>

        <div className="field">
          <label>Notes</label>
          <textarea rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Anything worth recording for next time" />
        </div>

        {err && <p className="vy-warning">⚠ {err.message}</p>}

        <button className="btn btn-primary btn-block" type="submit" disabled={submitting}>
          {submitting ? "Logging…" : "Log outcome"}
        </button>
      </form>
    </div>
  );
}
