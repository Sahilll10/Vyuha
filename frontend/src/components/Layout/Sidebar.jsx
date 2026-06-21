import "./Sidebar.css";

const NAV_ITEMS = [
  { key: "map", label: "Map", glyph: "◈" },
  { key: "simulate", label: "Simulate", glyph: "✦" },
  { key: "insights", label: "Insights", glyph: "▤" },
];

export default function Sidebar({ screen, onChangeScreen, replayActive, onToggleReplay }) {
  return (
    <nav className="vy-rail">
      <div className="vy-rail-mark" title="VYUHA — व्यूह">
        व्यूह
      </div>

      <div className="vy-rail-nav">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.key}
            className={`vy-rail-btn ${screen === item.key ? "is-active" : ""}`}
            onClick={() => onChangeScreen(item.key)}
            title={item.label}
          >
            <span className="vy-rail-glyph">{item.glyph}</span>
            <span className="vy-rail-label">{item.label}</span>
          </button>
        ))}
      </div>

      <button
        className={`vy-rail-btn vy-rail-replay ${replayActive ? "is-active" : ""}`}
        onClick={onToggleReplay}
        title="Historical replay"
      >
        <span className="vy-rail-glyph">{replayActive ? "⏸" : "▶"}</span>
        <span className="vy-rail-label">Replay</span>
      </button>
    </nav>
  );
}
