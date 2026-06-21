import { useMemo, useState } from "react";
import "./EventList.css";

const SEVERITY_RANK = { High: 3, Medium: 2, Low: 1, undefined: 0 };

export default function EventList({ events, loading, error, onSelectEvent, onRefresh, onLoadHistorical }) {
  const [sortBy, setSortBy] = useState("severity");

  const sorted = useMemo(() => {
    const list = [...(events || [])];
    if (sortBy === "severity") {
      list.sort((a, b) => SEVERITY_RANK[b.prediction?.severity] - SEVERITY_RANK[a.prediction?.severity]);
    } else if (sortBy === "duration") {
      list.sort(
        (a, b) => (b.prediction?.duration_median_mins || 0) - (a.prediction?.duration_median_mins || 0)
      );
    } else if (sortBy === "recent") {
      list.sort((a, b) => new Date(b.start_datetime || 0) - new Date(a.start_datetime || 0));
    }
    return list;
  }, [events, sortBy]);

  return (
    <div className="vy-eventlist">
      <div className="vy-eventlist-header">
        <div>
          <div className="eyebrow">Active incidents</div>
          <h3>{events?.length ?? 0} on the board</h3>
        </div>
        <button className="btn" onClick={onRefresh} title="Refresh">
          ↻
        </button>
      </div>

      <div className="vy-eventlist-sort">
        {[
          ["severity", "Severity"],
          ["duration", "Duration"],
          ["recent", "Most recent"],
        ].map(([key, label]) => (
          <button
            key={key}
            className={`vy-sort-pill ${sortBy === key ? "is-active" : ""}`}
            onClick={() => setSortBy(key)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="vy-eventlist-body">
        {loading && <div className="empty-state">Loading active incidents…</div>}

        {error && (
          <div className="empty-state">
            <h3>Couldn't reach the backend</h3>
            <p>{error.message}</p>
            <button className="btn" onClick={onRefresh} style={{ marginTop: 10 }}>
              Retry
            </button>
          </div>
        )}

        {!loading && !error && sorted.length === 0 && (
          <div className="empty-state">
            <h3>No active incidents yet</h3>
            <p>Load the historical ASTraM dataset to populate the board, or use the Simulate tab to inject a what-if event.</p>
            {onLoadHistorical && (
              <button className="btn btn-primary" onClick={onLoadHistorical} style={{ marginTop: 12 }}>
                Load historical dataset
              </button>
            )}
          </div>
        )}

        {!loading &&
          !error &&
          sorted.map((ev) => (
            <button key={ev.id} className="vy-event-row" onClick={() => onSelectEvent(ev.id)}>
              <span className={`severity-badge ${(ev.prediction?.severity || "low").toLowerCase()}`}>
                {ev.prediction?.severity || "—"}
              </span>
              <span className="vy-event-row-main">
                <span className="vy-event-cause">{ev.event_cause.replaceAll("_", " ")}</span>
                <span className="vy-event-sub">{ev.corridor || "Non-corridor"} · {ev.police_station || "—"}</span>
              </span>
              <span className="vy-event-row-meta mono">
                {ev.prediction ? `${Math.round(ev.prediction.duration_median_mins)}m` : "…"}
              </span>
            </button>
          ))}
      </div>
    </div>
  );
}
