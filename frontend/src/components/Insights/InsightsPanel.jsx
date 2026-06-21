import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { useApi } from "../../hooks/useApi.js";
import { api } from "../../api/client.js";
import "./InsightsPanel.css";

const TOOLTIP_STYLE = {
  background: "#1a2130",
  border: "1px solid #364158",
  borderRadius: 4,
  fontSize: 12,
  color: "#edeff3",
};

function StatTile({ label, value, sub }) {
  return (
    <div className="vy-stat-tile">
      <span className="eyebrow">{label}</span>
      <span className="vy-stat-tile-value">{value}</span>
      {sub && <span className="vy-stat-tile-sub">{sub}</span>}
    </div>
  );
}

export default function InsightsPanel() {
  const summary = useApi(() => api.insightsSummary(), []);
  const hourly = useApi(() => api.insightsHourlyPattern(), []);
  const causes = useApi(() => api.insightsCauseStats(), []);
  const corridors = useApi(() => api.insightsCorridorStats(12), []);
  const discrepancy = useApi(() => api.insightsSeverityVsPriority(), []);
  const metrics = useApi(() => api.insightsModelMetrics(), []);

  const notReady =
    summary.error || hourly.error || causes.error || corridors.error || discrepancy.error;

  if (notReady) {
    return (
      <div className="vy-insights">
        <div className="empty-state">
          <h3>Insights aren't available yet</h3>
          <p>
            Run <code className="mono">python scripts/preprocess.py</code> on the backend, then restart the
            API, so the dashboard has a processed dataset to summarize.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="vy-insights">
      <div className="vy-insights-header">
        <div className="eyebrow">What the data tells us</div>
        <h2>Dataset insights</h2>
        <p>Reproduced live from the processed ASTraM dataset — not a static screenshot.</p>
      </div>

      {summary.data && (
        <div className="vy-stat-grid">
          <StatTile label="Total events" value={summary.data.total_events.toLocaleString()} />
          <StatTile
            label="Planned / Unplanned"
            value={`${summary.data.planned_count} / ${summary.data.unplanned_count}`}
            sub={`${((summary.data.planned_count / summary.data.total_events) * 100).toFixed(1)}% planned`}
          />
          <StatTile label="Road closure rate" value={`${summary.data.road_closure_rate_pct}%`} />
          <StatTile label="Corridors tracked" value={summary.data.unique_corridors} />
          <StatTile label="Junctions tracked" value={summary.data.unique_junctions} />
          <StatTile label="Police stations" value={summary.data.unique_police_stations} />
        </div>
      )}

      <section className="vy-insight-block">
        <h4>Hourly pattern — the heavy-vehicle curfew signature</h4>
        <p className="vy-insight-caption">
          Events spike sharply between 2–4 AM IST and trough in the late afternoon — tracking
          Bengaluru's heavy-vehicle entry curfew window (highlighted below), not random noise.
        </p>
        {hourly.data && (
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={hourly.data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#262e3f" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: "#8089a0" }} interval={1} />
              <YAxis tick={{ fontSize: 10, fill: "#8089a0" }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                {hourly.data.map((d, i) => (
                  <Cell key={i} fill={d.is_curfew_window ? "#ff9d2e" : "#364158"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </section>

      <section className="vy-insight-block">
        <h4>Events by cause</h4>
        <p className="vy-insight-caption">
          ~60% of all events are ordinary vehicle breakdowns, not the dramatic festival/rally cases the
          problem statement leads with — a credible system has to be good at both.
        </p>
        {causes.data && (
          <ResponsiveContainer width="100%" height={Math.max(220, causes.data.length * 26)}>
            <BarChart
              data={causes.data}
              layout="vertical"
              margin={{ top: 4, right: 24, left: 8, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#262e3f" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "#8089a0" }} />
              <YAxis
                type="category"
                dataKey="cause"
                width={110}
                tick={{ fontSize: 10.5, fill: "#c5cad6" }}
                tickFormatter={(v) => v.replaceAll("_", " ")}
              />
              <Tooltip contentStyle={TOOLTIP_STYLE} formatter={(v, name) => [v, name === "count" ? "events" : name]} />
              <Bar dataKey="count" fill="#5ab8ff" radius={[0, 2, 2, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </section>

      <section className="vy-insight-block">
        <h4>Top corridors by event volume</h4>
        {corridors.data && (
          <ResponsiveContainer width="100%" height={Math.max(220, corridors.data.length * 24)}>
            <BarChart
              data={corridors.data}
              layout="vertical"
              margin={{ top: 4, right: 24, left: 8, bottom: 4 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#262e3f" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "#8089a0" }} />
              <YAxis type="category" dataKey="corridor" width={130} tick={{ fontSize: 10.5, fill: "#c5cad6" }} />
              <Tooltip contentStyle={TOOLTIP_STYLE} />
              <Bar dataKey="count" fill="#23d18b" radius={[0, 2, 2, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </section>

      <section className="vy-insight-block">
        <h4>Derived severity vs. raw priority</h4>
        <p className="vy-insight-caption">
          Where these disagree, our model is surfacing real disruption (closure rate) the manually-assigned
          priority field misses — e.g. tree-fall events are often tagged Low priority despite a high closure rate.
        </p>
        {discrepancy.data && (
          <div className="vy-discrepancy-list">
            {discrepancy.data.map((row) => (
              <div key={row.cause} className={`vy-discrepancy-row ${row.discrepancy ? "is-flagged" : ""}`}>
                <div className="vy-discrepancy-cause">{row.cause.replaceAll("_", " ")}</div>
                <div className="vy-discrepancy-bars">
                  <div className="vy-discrepancy-bar-row">
                    <span className="vy-discrepancy-bar-label">raw priority</span>
                    <div className="vy-discrepancy-bar-track">
                      <div className="vy-discrepancy-bar raw" style={{ width: `${row.raw_priority_high_pct}%` }} />
                    </div>
                    <span className="vy-discrepancy-bar-pct mono">{row.raw_priority_high_pct}%</span>
                  </div>
                  <div className="vy-discrepancy-bar-row">
                    <span className="vy-discrepancy-bar-label">ML severity</span>
                    <div className="vy-discrepancy-bar-track">
                      <div className="vy-discrepancy-bar ml" style={{ width: `${row.ml_severity_high_pct}%` }} />
                    </div>
                    <span className="vy-discrepancy-bar-pct mono">{row.ml_severity_high_pct}%</span>
                  </div>
                </div>
                <p className="vy-discrepancy-note">{row.note}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="vy-insight-block">
        <h4>Model performance</h4>
        {metrics.data ? (
          <div className="vy-metrics-grid">
            <div className="vy-metric-card">
              <span className="eyebrow">Severity classifier</span>
              <span className="vy-metric-value">
                {metrics.data.severity ? `${(metrics.data.severity.test_accuracy * 100).toFixed(1)}%` : "—"}
              </span>
              <span className="vy-metric-sub">held-out accuracy</span>
            </div>
            <div className="vy-metric-card">
              <span className="eyebrow">Closure classifier</span>
              <span className="vy-metric-value">
                {metrics.data.closure?.test_roc_auc != null ? metrics.data.closure.test_roc_auc.toFixed(3) : "—"}
              </span>
              <span className="vy-metric-sub">ROC-AUC</span>
            </div>
            <div className="vy-metric-card">
              <span className="eyebrow">Duration model</span>
              <span className="vy-metric-value">
                {metrics.data.duration?.concordance_index != null
                  ? metrics.data.duration.concordance_index.toFixed(3)
                  : "—"}
              </span>
              <span className="vy-metric-sub">concordance index</span>
            </div>
          </div>
        ) : (
          <p className="vy-rationale">
            No training metrics yet — run <code className="mono">python scripts/train_models.py</code> on the
            backend to populate this section.
          </p>
        )}
      </section>
    </div>
  );
}
