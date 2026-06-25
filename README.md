# VYUHA — व्यूह

### Predictive & Prescriptive Event-Response System for Bengaluru Traffic
**Gridlock Hackathon 2.0 — Flipkart × Bengaluru Traffic Police, Phase 2**

>Deployment:https://vyuha-deploy.vercel.app/
> "Vyuha" (व्यूह) is Sanskrit for a strategic battle formation — the deliberate
> arrangement of forces to respond to a threat. Fitting for a system whose
> entire job is to arrange manpower, barricades, and diversions around a
> traffic incident.

---

## What this is

Bengaluru Traffic Police logs ~8,000 events a month — breakdowns, accidents,
festivals, processions, VIP movement, construction — with no system that
forecasts impact in advance or recommends a response. VYUHA closes that gap
end to end:

1. **Forecasts** severity, expected duration (with a confidence range), and
   road-closure probability for any event, planned or unplanned.
2. **Prescribes** a complete response: how many officers, what barricade
   plan, and 2–3 ranked diversion routes around the affected segment.
3. **Demonstrates itself live** via a what-if injector — submit a
   hypothetical incident on the map and watch the full pipeline run end to
   end in under a second.
4. **Closes the loop** — a minimal but real post-event feedback mechanism
   that folds actual outcomes back into the next training run.

Most teams attacking this problem statement build a severity classifier and
a dashboard and stop. The prescriptive half — manpower, barricades, *and*
diversions, all actually generated rather than hand-waved — is what this
project leads with, because that's what the problem statement explicitly
asks for and explicitly calls "experience-driven" today.

---

## Project structure

```
vyuha/
├── backend/     ← Parts 1+2: data pipeline, ML models, recommendation engine, FastAPI
└── frontend/    ← Part 3: React + Leaflet command dashboard
```

The backend was kept as a single FastAPI service (rather than splitting the
recommender into a separate microservice) deliberately — for a one-week
hackathon, one deployable unit with a clean internal module boundary
(`app/ml/` vs `app/recommender/`) is far lower risk than two services that
have to stay in sync, and nothing in the architecture prevents splitting
them later if the system needs to scale independently.

---

## Quick start

### 1. Backend

```bash
cd backend
pip install -r requirements.txt          # use --break-system-packages if your pip needs it
cp .env.example .env

# Place the raw ASTraM export here:
cp /path/to/Astram_event_data_anonymized.csv data/raw/astram_events.csv

python scripts/preprocess.py             # clean + label the dataset (~seconds)
python scripts/train_models.py           # train all 3 models (~2-5 min on CPU)
python run.py                            # → http://localhost:8000  (docs at /docs)
```

Once it's running, load the historical dataset into the live API so the map
has something to show:

```bash
curl -X POST http://localhost:8000/events/load-historical
```

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env                     # only needed if the backend isn't on :8000
npm run dev                              # → http://localhost:5173
```

Open the app, and you should see active incidents on the map immediately
after the `load-historical` call above. Use the **Simulate** tab to inject a
what-if event — this is the demo centerpiece (roadmap section 8.2).

---

## Architecture

```
Raw CSV (8,173 ASTraM events, Nov 2023 – Apr 2024)
        │
        ▼  scripts/preprocess.py
Cleaned + labeled dataset (parquet)
  ├─ timezone-safe IST conversion, cause/junction/priority normalization
  ├─ censoring-aware duration_mins + observed flag (survival-analysis ready)
  └─ composite severity label (closure × cause weight × duration bucket)
        │
        ▼  scripts/train_models.py
  ┌─────────────────────────────────────────────────────────┐
  │  FeatureEngineer (frozen vocab, recurrence lookups)      │
  │       │                                                   │
  │       ├─ SeverityModel    (LightGBM, 3-class)            │
  │       ├─ ClosureModel     (LightGBM, binary)              │
  │       └─ DurationModel    (lifelines WeibullAFTFitter,    │
  │                             handles ~65% right-censored)  │
  └─────────────────────────────────────────────────────────┘
        │  saved_models/*.joblib
        ▼
  FastAPI (app/main.py)
  ├─ /events     simulate · load-historical · active · replay · feedback
  ├─ /predict    raw forecast, scored or unscored
  ├─ /recommend  manpower · barricade · diversion · station-allocation
  └─ /insights   summary · hourly-pattern · cause-stats · corridor-stats ·
                 severity-vs-priority · model-metrics
        │
        ▼
  app/recommender/response_card.py — ties prediction + manpower +
  barricade + diversion into the single Event Response Card artifact
        │
        ▼
  React + Leaflet command dashboard (frontend/)
  ├─ Command map        active incidents, colored by severity
  ├─ Response Card       full forecast + recommendations, drawn on the map
  ├─ Simulate            the what-if injector (the live demo moment)
  ├─ Insights            EDA reproduced live, not screenshotted
  └─ Feedback            post-event outcome logging → retraining loop
```

---

## Key design decisions (and why)

1. **Survival analysis for duration, not a regressor.** Only ~35% of events
   have a clean `closed_datetime`. Training a regressor on just that subset
   biases toward the easy/fast cases that happen to get logged out cleanly.
   Every event is instead a survival-time observation — censored at
   `modified_datetime` when no real closure timestamp exists — fit with
   `lifelines.WeibullAFTFitter`. This gives a median *and* a [10th, 90th]
   percentile range: "expect 35–70 min" instead of a single number that's
   quietly wrong for the majority of the dataset.

2. **A composite severity label, not a copy of the raw `priority` field.**
   Raw `priority` and physical disruption disagree for specific causes —
   `tree_fall` is tagged Low priority 67% of the time despite a 39%
   road-closure rate. The derived severity combines closure, a hand-set
   cause weight, and duration bucket, and `/insights/severity-vs-priority`
   surfaces exactly where the two disagree — concrete evidence the model
   adds information the existing manual field doesn't have.

3. **The curfew-window feature, built in explicitly.** Events spike ~10x
   between 2–4 AM IST and trough in the late afternoon, tracking
   Bengaluru's heavy-vehicle entry curfew almost exactly. Rather than let a
   tree model rediscover this implicitly, `is_curfew_window` is a first-
   class engineered feature, and every raw timestamp is converted from UTC
   to IST through one single, tested code path (`app/utils/time_utils.py`)
   — a silent UTC/IST mismatch would quietly shift this entire insight by
   5h30m without raising an error.

4. **Two response timelines, not one model forced to do both jobs.**
   Unplanned events (94.3%) need fast reactive forecasting; planned events
   (5.7%, but the festivals/rallies/VIP-movement cases the problem
   statement leads with) need proactive pre-positioning. Inverse-frequency
   sample weighting by `event_cause` keeps the rare-but-important causes
   (`vip_movement`, `public_event`, `procession`, `protest`) from being
   drowned out by the 60%-majority `vehicle_breakdown` class.

5. **The Kannada-language field text is handled, not dropped.** Most teams
   will either ignore `description` entirely or drop non-English rows. A
   small multilingual keyword tagger (`app/utils/nlp_tags.py`) extracts
   operational signals — towing in progress, already cleared, severity
   language — from real bilingual field reports, feeding auxiliary boolean
   features into the tabular models.

6. **An offline-safe routing fallback, reported honestly.** The diversion
   engine prefers a real OSMnx/OpenStreetMap road graph, but live-demo
   network access (conference wifi, judging-room firewalls) is never
   guaranteed. The fallback graph is built directly from the dataset's own
   H3-bucketed coordinates — real Bengaluru geography, zero internet
   required — and every response reports `routing_mode` (`"osm"` or
   `"fallback"`) plus a plain-language note. It never silently pretends the
   fallback is the real road network.

7. **A real, if minimal, post-event learning loop.** The problem statement
   names "no post-event learning system" as an explicit gap. `POST
   /events/feedback` logs actual outcomes, and
   `scripts/retrain_from_feedback.py` folds them back into the processed
   dataset and re-runs the full training pipeline — a "Retrain now" action
   away from being wired into the dashboard, not a slide bullet with no
   mechanism behind it.

---

## API reference

| Method | Path | Description |
|---|---|---|
| GET | `/health` | predictor / insights-cache / road-graph status |
| POST | `/events/simulate` | the what-if injector — full Event Response Card in one call |
| POST | `/events/load-historical` | bulk-load the cleaned CSV into the live DB |
| GET | `/events/active` | active incidents for the command map |
| GET | `/events/replay/stream?offset=&limit=` | chronological window for replay mode |
| GET | `/events/{id}` | one event + its latest prediction |
| GET | `/events/{id}/response-card` | full Response Card for an existing event |
| POST | `/events/feedback` | log a real post-event outcome |
| POST | `/predict/event` | score a new event without persisting it |
| POST | `/predict/event/{id}` | score and persist a prediction for an existing event |
| POST | `/recommend/manpower` | standalone manpower recommendation |
| POST | `/recommend/barricade` | standalone barricade plan |
| POST | `/recommend/diversion` | standalone diversion routes |
| POST | `/recommend/station-allocation` | greedy allocator across concurrent incidents at one station |
| GET | `/insights/summary` | dataset overview |
| GET | `/insights/hourly-pattern` | the 2 AM curfew insight |
| GET | `/insights/cause-stats` | per-cause breakdown |
| GET | `/insights/corridor-stats` | per-corridor breakdown |
| GET | `/insights/severity-vs-priority` | the derived-vs-raw discrepancy chart |
| GET | `/insights/model-metrics` | held-out accuracy/AUC/concordance + top features |

Full interactive docs (request/response schemas, try-it-out) are served at
`/docs` once the backend is running.

---

## Known limitations (stated honestly, not hidden)

- **Sandbox-authored, not sandbox-trained.** This codebase was written and
  syntax/logic-verified (unit tests against synthetic edge cases for the
  cleaning, censoring, severity-label, feature-engineering, and routing
  logic — see the bugs those tests actually caught, below) in an
  environment without network access and without the real ASTraM CSV
  present, so the model-training step itself has not been run end to end
  here. Every module that *could* be exercised without the full dependency
  stack (`pandas`/`numpy`/`networkx`, all available) was — including two
  real bugs that were found and fixed this way:
  1. `clean_raw_events` originally parsed timestamps row-by-row with
     `.apply()`, which silently produced `object`-dtype columns instead of
     real `datetime64` columns and broke duration arithmetic. Fixed to use
     vectorized `pd.to_datetime(..., utc=True)`.
  2. `FeatureEngineer.fit` could produce a duplicate `"unknown"` category
     for columns (like `veh_type`) whose cleaning step already emits the
     literal string `"unknown"`, crashing `pd.Categorical` construction.
     Fixed by de-duplicating the frozen vocabulary before appending the
     sentinel.

  Run `scripts/preprocess.py` and `scripts/train_models.py` against the
  real CSV before the demo and read the console output — it reproduces the
  roadmap's headline EDA numbers (median duration, closure rates by cause,
  the 2 AM spike) as a sanity check that everything lines up.

- **Planned-event sample size is genuinely small** (467 rows). Inverse-
  frequency weighting helps, but don't expect production-grade precision on
  `vip_movement`/`protest` (20 and 15 historical rows respectively) — this
  is named directly in the roadmap as a real trap, not glossed over here.

- **The fallback routing graph is "as the crow flies,"** not true road
  geometry, when OSM access isn't available. It's clearly labeled as such
  in every API response (`routing_mode: "fallback"` + a plain-language
  note) rather than silently presented as real.

- **The retraining loop is demo-minimal by design** — a script, not a
  scheduled job — exactly matching what the roadmap scoped for a one-week
  build. Wiring it to a dashboard "Retrain now" button is a clean, small
  next step (`scripts/retrain_from_feedback.py` already does the heavy
  lifting; it just needs an endpoint wrapper).

---

## What we'd build next with more time or data

- A live CCTV/GPS feed integration replacing the historical-replay/what-if
  simulation layer with real-time ASTraM events.
- The spatio-temporal graph model stretch goal (roadmap 6.5) — modeling
  spillover congestion between adjacent junctions with a lightweight GNN.
- A formal linear-program version of the manpower allocator (PuLP),
  maximizing weighted severity coverage subject to a real per-station
  headcount constraint, replacing the current greedy baseline.
- Scheduled (not button-triggered) retraining, with before/after held-out
  metrics surfaced automatically on the Insights screen.
- Multilingual sentence embeddings (e.g. `intfloat/multilingual-e5-small`)
  in place of the current keyword tagger, plus a "similar past incidents"
  nearest-neighbor lookup surfaced directly on the Response Card.

---

## Credits

Built for Gridlock Hackathon 2.0 (Flipkart × Bengaluru Traffic Police),
against the BTP ASTraM event export. व्यूह.
