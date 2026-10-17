"use client";
import { useState } from "react";

const api = () => String(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export default function WhatsAppCampaigns({ tenantId, token }: { tenantId: string; token: string }) {
  const [name, setName] = useState("");
  const [template, setTemplate] = useState("Hello {Name}, this is a test message!");
  const [csvData, setCsvData] = useState("917022147300,John Doe\n919876543210,Jane Smith");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  const handleStart = async () => {
    if (!name || !template || !csvData) return;
    setBusy(true);
    setStatus("Creating campaign...");

    // Parse CSV (Phone, Name)
    const recipients = csvData.split("\n").map(line => {
      const [phone, recipientName] = line.split(",");
      return { phone: phone.trim(), name: (recipientName || "").trim() };
    }).filter(r => r.phone);

    try {
      const res = await fetch(`${api()}/api/v1/tenants/${tenantId}/campaigns`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify({ name, template_text: template, recipients })
      });
      const data = await res.json();
      
      if (!res.ok) throw new Error(data.detail || "Failed to create");

      setStatus("Starting campaign...");
      await fetch(`${api()}/api/v1/tenants/${tenantId}/campaigns/${data.campaign_id}/start`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` }
      });

      setStatus("✅ Campaign is running in the background! Check the dashboard later.");
      setName("");
    } catch (e: any) {
      setStatus("❌ " + e.message);
    }
    setBusy(false);
  };

  return (
    <div className="p-6 border rounded-lg bg-white shadow-sm max-w-2xl">
      <h2 className="text-xl font-bold mb-4">Create Bulk Campaign</h2>
      
      <div className="mb-4">
        <label className="block text-sm font-bold mb-1">Campaign Name</label>
        <input 
          className="border p-2 w-full rounded" 
          value={name} onChange={e => setName(e.target.value)} 
          placeholder="e.g. Diwali Offer 2026" 
        />
      </div>

      <div className="mb-4">
        <label className="block text-sm font-bold mb-1">Message Template</label>
        <textarea 
          className="border p-2 w-full rounded h-24" 
          value={template} onChange={e => setTemplate(e.target.value)} 
          placeholder="Use {Name} for personalization" 
        />
        <p className="text-xs text-gray-500 mt-1">Placeholders: {"{Name}"}, {"{Phone}"}</p>
      </div>

      <div className="mb-4">
        <label className="block text-sm font-bold mb-1">Recipients (CSV Format: Phone, Name)</label>
        <textarea 
          className="border p-2 w-full rounded h-32 font-mono text-sm" 
          value={csvData} onChange={e => setCsvData(e.target.value)} 
        />
      </div>

      <button 
        onClick={handleStart} 
        disabled={busy}
        className="bg-green-600 text-white px-6 py-2 rounded font-bold disabled:opacity-50"
      >
        {busy ? "Starting..." : "Start Campaign"}
      </button>

      {status && <p className="mt-4 text-sm font-medium">{status}</p>}
    </div>
  );
}