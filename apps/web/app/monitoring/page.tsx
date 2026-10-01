"use client";
import MonitoringPanel from "../../../components/MonitoringPanel";

export default function MonitoringPage() {
  return (
    <div>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 26, letterSpacing: "-0.03em", color: "#17213a" }}>
          Monitoring
        </h1>
        <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 13 }}>
          Live health of every component, auto-recovery actions, and alerts.
        </p>
      </div>
      <MonitoringPanel />
    </div>
  );
}