import { useState } from "react";
import FeedbackForm from "../Feedback/FeedbackForm.jsx";
import "./ResponseCard.css";

function fmtMins(m) {
  if (m == null) return "—";
  if (m < 60) return `${Math.round(m)} min`;
  const h = Math.floor(m / 60);
  const rem = Math.round(m % 60);
  return `${h}h ${rem}m`;
}

export default function ResponseCard({ card, loading, error, onBack, onClose, onLoggedFeedback }) {
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  if (loading) {
    return (
      <div className="vy-card vy-card-loading">
        <div className="empty-state">
          <span className="spin" style={{ fontSize: 22 }}>◌</span>
          <h3>Running the pipeline…</h3>
          <p>Forecasting severity, duration, and closure probability, then generating recommendations.</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="vy-card">
        <div className="empty-state">
          <h3>Couldn't build the Response Card</h3>
          <p>{error.message}</p>
          {onBack && (
            <button className="btn" onClick={onBack} style={{ marginTop: 12 }}>
              ← Back
            </button>
          )}
        </div>
      </div>
    );
  }

  if (!card) return null;

  const { event, prediction, manpower, barricade, diversion } = card;
  const severity = (prediction.severity || "low").toLowerCase();

  return (
    <div className="vy-card">
      <div className="vy-card-topbar">
        {onBack && (
          <button className="vy-back" onClick={onBack}>
            ← Back
          </button>
        )}
        {onClose && (
          <button className="vy-back" onClick={onClose}>
            ✕
          </button>
        )}
      </div>

      <div className="vy-card-header">
        <span className={`severity-badge ${severity}`}>{prediction.severity} severity</span>
        <h2>{event.event_cause.replaceAll("_", " ")}</h2>
        <div className="vy-card-sub mono">
          {event.id} · {event.corridor || "Non-corridor"} · {event.police_station || "station n/a"}
        </div>
        {event.address && <div className="vy-card-address">{event.address}</div>}
      </div>

      <div className="vy-card-stats">
        <div className="vy-stat">
          <span className="eyebrow">Confidence</span>
          <span className="vy-stat-value">{Math.round(prediction.severity_confidence * 100)}%</span>
        </div>
        <div className="vy-stat">
          <span className="eyebrow">Closure probability</span>
          <span className="vy-stat-value">{Math.round(prediction.closure_probability * 100)}%</span>
        </div>
        <div className="vy-stat">
          <span className="eyebrow">Expected duration</span>
          <span className="vy-stat-value">{fmtMins(prediction.duration_median_mins)}</span>
          <span className="vy-stat-range mono">
            {fmtMins(prediction.duration_lower_mins)} – {fmtMins(prediction.duration_upper_mins)}
          </span>
        </div>
      </div>

      <section className="vy-card-section">
        <h4>Manpower</h4>
        <div className="vy-manpower-row">
          <span className="vy-manpower-count">{manpower.officers}</span>
          <span className="vy-manpower-label">
            officer{manpower.officers === 1 ? "" : "s"} recommended
            {manpower.supervisor_required && <span className="vy-supervisor-tag">+ supervisor</span>}
          </span>
        </div>
        <ul className="vy-unit-list">
          {manpower.units.map((u, i) => (
            <li key={i}>{u}</li>
          ))}
        </ul>
        <p className="vy-rationale">{manpower.rationale}</p>
        {manpower.capacity_warning && <p className="vy-warning">⚠ {manpower.capacity_warning}</p>}
      </section>

      <section className="vy-card-section">
        <h4>Barricading</h4>
        <p className="vy-rationale">{barricade.summary}</p>
        <ul className="vy-point-list">
          {barricade.points.map((p, i) => (
            <li key={i}>
              <strong>{p.label}</strong>
              <span>{p.instruction}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="vy-card-section">
        <h4>Diversion routes</h4>
        {diversion.note && <p className="vy-rationale vy-note">{diversion.note}</p>}
        {diversion.routes.length === 0 ? (
          <p className="vy-rationale">No diversion needed for this event.</p>
        ) : (
          <ul className="vy-route-list">
            {diversion.routes.map((r) => (
              <li key={r.rank}>
                <span className={`vy-route-dot vy-route-dot-${r.rank}`} />
                <span className="vy-route-text">
                  <strong>Route {r.rank}</strong> — {r.distance_km} km, ~{r.estimated_minutes} min
                  {r.extra_distance_km > 0 && (
                    <span className="vy-route-extra"> (+{r.extra_distance_km} km)</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div className="vy-card-footer">
        <button className="btn btn-block" onClick={() => setFeedbackOpen(true)}>
          Log outcome / mark resolved
        </button>
      </div>

      {feedbackOpen && (
        <FeedbackForm
          eventId={event.id}
          onClose={() => setFeedbackOpen(false)}
          onSubmitted={() => {
            setFeedbackOpen(false);
            onLoggedFeedback?.();
          }}
        />
      )}
    </div>
  );
}
