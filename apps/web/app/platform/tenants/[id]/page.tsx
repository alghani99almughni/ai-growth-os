"use client";
import { useEffect } from "react";
import { useParams } from "next/navigation";

export default function PlatformTenantRedirect() {
  const params = useParams();
  const id = String(params?.id || "");

  useEffect(() => {
    if (id) {
      window.location.replace(`/dashboard?tenant=${encodeURIComponent(id)}`);
    }
  }, [id]);

  return <div style={{ padding: 80, textAlign: "center", color: "#75839a" }}>Opening tenant dashboard…</div>;
}