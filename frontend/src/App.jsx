import { useCallback, useEffect, useRef, useState } from "react";
import Sidebar from "./components/Layout/Sidebar.jsx";
import StatusBar from "./components/Layout/StatusBar.jsx";
import CommandMap from "./components/Map/CommandMap.jsx";
import EventList from "./components/Events/EventList.jsx";
import ResponseCard from "./components/ResponseCard/ResponseCard.jsx";
import SimulateForm from "./components/Simulate/SimulateForm.jsx";
import InsightsPanel from "./components/Insights/InsightsPanel.jsx";
import { useApi } from "./hooks/useApi.js";
import { api } from "./api/client.js";
import "./App.css";

const REPLAY_WINDOW = 60;
const REPLAY_TICK_MS = 2200;

export default function App() {
  const [screen, setScreen] = useState("map");

  // ── active events (Screen 1) ──
  const activeEvents = useApi(() => api.activeEvents(300), []);

  // ── system health, refreshed periodically for the status bar ──
  const health = useApi(() => api.health(), []);
  useEffect(() => {
    const id = setInterval(() => health.refetch(), 15000);
    return () => clearInterval(id);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── the single "currently displayed" Event Response Card ──
  const [activeCard, setActiveCard] = useState(null);
  const [cardLoading, setCardLoading] = useState(false);
  const [cardError, setCardError] = useState(null);

  const openEventCard = useCallback(async (eventId) => {
    setCardLoading(true);
    setCardError(null);
    setActiveCard(null);
    try {
      const card = await api.getResponseCard(eventId);
      setActiveCard(card);
    } catch (e) {
      setCardError(e);
    } finally {
      setCardLoading(false);
    }
  }, []);

  const closeCard = useCallback(() => {
    setActiveCard(null);
    setCardError(null);
  }, []);

  // ── what-if injector state ──
  const [pickMode, setPickMode] = useState(false);
  const [pickedCoords, setPickedCoords] = useState(null);
  const [simulating, setSimulating] = useState(false);

  async function handleSimulate(payload) {
    setSimulating(true);
    setCardError(null);
    try {
      const card = await api.simulateEvent(payload);
      setActiveCard(card);
      setPickMode(false);
      activeEvents.refetch();
    } catch (e) {
      setCardError(e);
    } finally {
      setSimulating(false);
    }
  }

  function handlePickLocation(coords) {
    setPickedCoords(coords);
    setPickMode(false);
  }

  async function handleLoadHistorical() {
    try {
      await api.loadHistorical();
      activeEvents.refetch();
      health.refetch();
    } catch (e) {
      // surfaced inline by EventList's error state on next refetch attempt
      console.error(e);
    }
  }

  // ── historical replay mode (roadmap 8.1) ──
  const [replayActive, setReplayActive] = useState(false);
  const [replayEvents, setReplayEvents] = useState([]);
  const replayOffsetRef = useRef(0);

  useEffect(() => {
    if (!replayActive) return;
    let cancelled = false;
    replayOffsetRef.current = 0;

    async function tick() {
      try {
        const batch = await api.replayStream(replayOffsetRef.current, REPLAY_WINDOW);
        if (cancelled) return;
        if (!batch || batch.length === 0) {
          replayOffsetRef.current = 0; // loop back to the start of the dataset
        } else {
          setReplayEvents(batch);
          replayOffsetRef.current += REPLAY_WINDOW;
        }
      } catch (e) {
        console.error("Replay tick failed", e);
      }
    }

    tick();
    const id = setInterval(tick, REPLAY_TICK_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [replayActive]);

  const mapEvents = replayActive ? replayEvents : activeEvents.data || [];

  return (
    <div className="vy-app">
      <Sidebar
        screen={screen}
        onChangeScreen={(s) => {
          setScreen(s);
          if (s !== "simulate") setPickMode(false);
        }}
        replayActive={replayActive}
        onToggleReplay={() => setReplayActive((v) => !v)}
      />

      <div className="vy-main">
        {screen === "insights" ? (
          <InsightsPanel />
        ) : (
          <div className="vy-workspace">
            <CommandMap
              events={mapEvents}
              selectedEventId={activeCard?.event?.id}
              onSelectEvent={openEventCard}
              pickMode={screen === "simulate" && pickMode}
              onPickLocation={handlePickLocation}
              responseCard={activeCard}
            />

            <aside className="vy-panel">
              {activeCard || cardLoading || cardError ? (
                <ResponseCard
                  card={activeCard}
                  loading={cardLoading}
                  error={cardError}
                  onBack={closeCard}
                  onLoggedFeedback={() => {
                    activeEvents.refetch();
                    closeCard();
                  }}
                />
              ) : screen === "map" ? (
                <EventList
                  events={activeEvents.data}
                  loading={activeEvents.loading}
                  error={activeEvents.error}
                  onSelectEvent={openEventCard}
                  onRefresh={activeEvents.refetch}
                  onLoadHistorical={handleLoadHistorical}
                />
              ) : (
                <SimulateForm
                  pickMode={pickMode}
                  onTogglePickMode={setPickMode}
                  pickedCoords={pickedCoords}
                  onSimulate={handleSimulate}
                  submitting={simulating}
                />
              )}
            </aside>
          </div>
        )}

        <StatusBar
          health={health.data}
          eventCount={replayActive ? replayEvents.length : activeEvents.data?.length}
          lastUpdated={health.data ? new Date().toLocaleTimeString() : null}
        />
      </div>
    </div>
  );
}
