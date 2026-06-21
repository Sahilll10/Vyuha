import { useEffect, useState } from "react";
import "./SimulateForm.css";

const CAUSES = [
  "vehicle_breakdown", "accident", "pot_holes", "construction", "water_logging",
  "tree_fall", "road_conditions", "congestion", "public_event", "procession",
  "vip_movement", "protest", "debris", "others",
];

const CORRIDORS = [
  "Mysore Road", "Bellary Road 1", "Bellary Road 2", "Tumkur Road", "Hosur Road",
  "ORR North 1", "ORR North 2", "ORR East 1", "ORR West 1", "Old Madras Road",
  "Magadi Road", "Bannerghata Road", "CBD 1", "CBD 2", "Non-corridor",
];

const VEH_TYPES = [
  "bmtc_bus", "heavy_vehicle", "lcv", "private_bus", "private_car", "truck",
  "ksrtc_bus", "taxi", "auto", "others",
];

const DEFAULT_FORM = {
  event_type: "unplanned",
  event_cause: "vehicle_breakdown",
  latitude: "12.9716",
  longitude: "77.5946",
  endlatitude: "",
  endlongitude: "",
  address: "",
  corridor: "",
  police_station: "",
  junction: "",
  zone: "",
  veh_type: "",
  description: "",
};

export default function SimulateForm({ pickMode, onTogglePickMode, pickedCoords, onSimulate, submitting }) {
  const [form, setForm] = useState(DEFAULT_FORM);

  useEffect(() => {
    if (!pickedCoords) return;
    setForm((f) => ({
      ...f,
      latitude: pickedCoords.lat.toFixed(6),
      longitude: pickedCoords.lng.toFixed(6),
    }));
  }, [pickedCoords]);

  function update(field, value) {
    setForm((f) => ({ ...f, [field]: value }));
  }

  function handleSubmit(e) {
    e.preventDefault();
    const payload = {
      event_type: form.event_type,
      event_cause: form.event_cause,
      latitude: Number(form.latitude),
      longitude: Number(form.longitude),
      endlatitude: form.endlatitude ? Number(form.endlatitude) : null,
      endlongitude: form.endlongitude ? Number(form.endlongitude) : null,
      address: form.address || null,
      corridor: form.corridor || null,
      police_station: form.police_station || null,
      junction: form.junction || null,
      zone: form.zone || null,
      veh_type: form.veh_type || null,
      description: form.description || null,
    };
    onSimulate(payload);
  }

  return (
    <div className="vy-simulate">
      <div className="vy-simulate-header">
        <div className="eyebrow">What-if injector</div>
        <h3>Simulate a new event</h3>
        <p>
          Submit a hypothetical incident and watch the full pipeline run live — severity, duration,
          closure probability, then manpower, barricades, and diversion routes, all in one pass.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="vy-simulate-form">
        <div className="field-row">
          <div className="field">
            <label>Event type</label>
            <select value={form.event_type} onChange={(e) => update("event_type", e.target.value)}>
              <option value="unplanned">Unplanned (reactive)</option>
              <option value="planned">Planned (proactive)</option>
            </select>
          </div>
          <div className="field">
            <label>Cause</label>
            <select value={form.event_cause} onChange={(e) => update("event_cause", e.target.value)}>
              {CAUSES.map((c) => (
                <option key={c} value={c}>
                  {c.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="field">
          <label>Location</label>
          <div className="vy-coord-row">
            <input
              type="number"
              step="0.000001"
              value={form.latitude}
              onChange={(e) => update("latitude", e.target.value)}
              placeholder="latitude"
            />
            <input
              type="number"
              step="0.000001"
              value={form.longitude}
              onChange={(e) => update("longitude", e.target.value)}
              placeholder="longitude"
            />
            <button
              type="button"
              className={`btn ${pickMode ? "btn-primary" : ""}`}
              onClick={() => onTogglePickMode(!pickMode)}
            >
              {pickMode ? "Picking…" : "Pick on map"}
            </button>
          </div>
          <span className="field-hint">Defaults to central Bengaluru — click "Pick on map" to place it precisely.</span>
        </div>

        <div className="field">
          <label>End location (optional — linear events like processions or fallen trees)</label>
          <div className="vy-coord-row">
            <input
              type="number"
              step="0.000001"
              value={form.endlatitude}
              onChange={(e) => update("endlatitude", e.target.value)}
              placeholder="end latitude"
            />
            <input
              type="number"
              step="0.000001"
              value={form.endlongitude}
              onChange={(e) => update("endlongitude", e.target.value)}
              placeholder="end longitude"
            />
          </div>
        </div>

        <div className="field">
          <label>Address</label>
          <input value={form.address} onChange={(e) => update("address", e.target.value)} placeholder="e.g. Silk Board Junction, Hosur Road" />
        </div>

        <div className="field-row">
          <div className="field">
            <label>Corridor</label>
            <input
              list="vy-corridor-list"
              value={form.corridor}
              onChange={(e) => update("corridor", e.target.value)}
              placeholder="Non-corridor"
            />
            <datalist id="vy-corridor-list">
              {CORRIDORS.map((c) => (
                <option key={c} value={c} />
              ))}
            </datalist>
          </div>
          <div className="field">
            <label>Junction</label>
            <input value={form.junction} onChange={(e) => update("junction", e.target.value)} placeholder="e.g. SilkBoardJunc" />
          </div>
        </div>

        <div className="field-row">
          <div className="field">
            <label>Police station</label>
            <input value={form.police_station} onChange={(e) => update("police_station", e.target.value)} placeholder="e.g. HSR" />
          </div>
          <div className="field">
            <label>Zone</label>
            <input value={form.zone} onChange={(e) => update("zone", e.target.value)} placeholder="e.g. South Zone 1" />
          </div>
        </div>

        <div className="field">
          <label>Vehicle type</label>
          <select value={form.veh_type} onChange={(e) => update("veh_type", e.target.value)}>
            <option value="">Not applicable</option>
            {VEH_TYPES.map((v) => (
              <option key={v} value={v}>
                {v.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </div>

        <div className="field">
          <label>Description (English or Kannada)</label>
          <textarea
            rows={3}
            value={form.description}
            onChange={(e) => update("description", e.target.value)}
            placeholder="e.g. tyre blast and wheel jam, mechanic on the way"
          />
        </div>

        <button className="btn btn-primary btn-block" type="submit" disabled={submitting}>
          {submitting ? "Running pipeline…" : "Simulate event →"}
        </button>
      </form>
    </div>
  );
}
