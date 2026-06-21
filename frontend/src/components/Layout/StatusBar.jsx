import "./StatusBar.css";

function Dot({ ok }) {
  return <span className={`vy-status-dot ${ok ? "is-ok" : "is-down"}`} />;
}

export default function StatusBar({ health, eventCount, lastUpdated }) {
  const predictorOk = !!health?.predictor?.loaded;
  const insightsOk = !!health?.insights_cache?.loaded;
  const roadGraphMode = health?.road_graph?.mode;

  return (
    <div className="vy-statusbar">
      <div className="vy-status-item">
        <Dot ok={predictorOk} />
        <span>predictor {predictorOk ? "ready" : "not loaded"}</span>
      </div>
      <div className="vy-status-item">
        <Dot ok={insightsOk} />
        <span>insights {insightsOk ? "ready" : "not loaded"}</span>
      </div>
      <div className="vy-status-item">
        <Dot ok={!!roadGraphMode} />
        <span>road graph [{roadGraphMode || "—"}]</span>
      </div>
      <div className="vy-status-spacer" />
      <div className="vy-status-item mono">{eventCount ?? "—"} events on board</div>
      {lastUpdated && <div className="vy-status-item mono">updated {lastUpdated}</div>}
    </div>
  );
}
