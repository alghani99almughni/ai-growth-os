"use client";
import { useEffect, useState } from "react";

const api = () => process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type LoyaltyRule = {
  id: string;
  event_type: string;
  name: string;
  points: number;
  is_active: boolean;
  config: Record<string, any>;
};

type LoyaltyReward = {
  id: string;
  name: string;
  points_cost: number;
  description: string | null;
  is_active: boolean;
};

export default function LoyaltyPanel({
  tenantId,
  token,
}: {
  tenantId: string;
  token: string;
}) {
  const [enabled, setEnabled] = useState<boolean>(true);
  const [rules, setRules] = useState<LoyaltyRule[]>([]);
  const [rewards, setRewards] = useState<LoyaltyReward[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const authHeaders = () => ({ Authorization: "Bearer " + token });

  async function jget(path: string) {
    const r = await fetch(api() + path, { headers: authHeaders(), cache: "no-store" });
    const raw = await r.text();
    let x: any = {};
    try { x = JSON.parse(raw); } catch {}
    if (!r.ok) throw new Error(x?.detail || "Request failed");
    return x;
  }

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const [summaryRes, rulesRes, rewardsRes] = await Promise.all([
        jget(`/api/v1/tenants/${tenantId}/loyalty`),
        jget(`/api/v1/tenants/${tenantId}/loyalty-rules`),
        jget(`/api/v1/tenants/${tenantId}/loyalty-rewards`),
      ]);
      setEnabled(Boolean(summaryRes?.enabled));
      setRules(rulesRes.items || []);
      setRewards(rewardsRes.items || []);
    } catch (e: any) {
      setError(e.message || "Could not load loyalty settings");
    }
    setLoading(false);
  }

  useEffect(() => {
    if (tenantId) void loadAll();
  }, [tenantId]);

  return (
    <section className="card">
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <div>
          <h2 style={{ margin: 0 }}>🎁 Loyalty program</h2>
          <p style={{ margin: "4px 0 0", color: "#75839a", fontSize: 13 }}>
            {enabled ? "Program is active." : "Program is disabled for this business."}
          </p>
        </div>
        <button className="btn-ghost" onClick={loadAll} disabled={loading}>
          {loading ? "Loading…" : "Refresh"}
        </button>
      </div>

      {error && <p style={{ color: "#b00", marginTop: 12 }}>{error}</p>}

      {/* Rules */}
      <div style={{ marginTop: 24 }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>
          Earning rules ({rules.length})
        </h3>

        {rules.length === 0 && !loading && (
          <div className="empty-state">
            <h3>No rules yet</h3>
            <p>
              Loyalty rules define how customers earn points — e.g. 1 point per ₹100 spent, 10
              points for a review.
            </p>
          </div>
        )}

        {rules.map((r) => (
          <article
            key={r.id}
            className="card"
            style={{ marginBottom: 10, padding: 14, background: "#fff" }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <strong style={{ fontSize: 14 }}>{r.name}</strong>
              <span className="badge badge-blue">+{r.points} pts</span>
              <span className="badge badge-grey">{r.event_type}</span>
              {!r.is_active && <span className="badge badge-grey">inactive</span>}
            </div>
            {r.config && Object.keys(r.config).length > 0 && (
              <p
                style={{
                  margin: "6px 0 0",
                  fontFamily: "monospace",
                  fontSize: 11,
                  color: "#75839a",
                }}
              >
                {JSON.stringify(r.config)}
              </p>
            )}
          </article>
        ))}
      </div>

      {/* Rewards */}
      <div style={{ marginTop: 28 }}>
        <h3 style={{ margin: "0 0 12px", fontSize: 14 }}>
          Rewards catalog ({rewards.length})
        </h3>

        {rewards.length === 0 && !loading && (
          <div className="empty-state">
            <h3>No rewards yet</h3>
            <p>
              Rewards are things customers can redeem points for — a free coffee, ₹100 off, an
              upgrade.
            </p>
          </div>
        )}

        {rewards.map((rw) => (
          <article
            key={rw.id}
            className="card"
            style={{ marginBottom: 10, padding: 14, background: "#fff" }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                gap: 12,
                flexWrap: "wrap",
              }}
            >
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <strong style={{ fontSize: 14 }}>{rw.name}</strong>
                  <span className="badge badge-purple">{rw.points_cost} pts</span>
                  {!rw.is_active && <span className="badge badge-grey">inactive</span>}
                </div>
                {rw.description && (
                  <p style={{ margin: "6px 0 0", color: "#75839a", fontSize: 12 }}>
                    {rw.description}
                  </p>
                )}
              </div>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}