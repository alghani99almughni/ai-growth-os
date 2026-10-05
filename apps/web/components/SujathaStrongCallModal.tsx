"use client";

import { useState } from "react";
import VoiceCallModal from "./VoiceCallModal";

type Props = {
  slug: string;
  businessName: string;
  existingCustomerId?: string;
  agentGender?: "male" | "female";
  onCustomerIdentified?: (customerId: string) => void;
  onClose: () => void;
};

/**
 * Strong-call presentation layer for pilot tenants.
 * The proven VoiceCallModal remains the call engine.
 * This shell adds persistent minimize/restore behavior without touching
 * the SS Nutritions implementation.
 */
export default function SujathaStrongCallModal({
  slug,
  businessName,
  existingCustomerId,
  agentGender = "female",
  onCustomerIdentified,
  onClose,
}: Props) {
  const [minimized, setMinimized] = useState(false);

  return (
    <>
      <div className={`strong-call-shell ${minimized ? "is-minimized" : ""}`}>
        <div className="strong-call-header">
          <div className="strong-call-brand">
            <div className="strong-call-logo">AI</div>
            <div>
              <strong>AI GROWTH OS</strong>
              <span>SECURE CALL</span>
            </div>
          </div>

          <div className="strong-call-meta">
            <span className="strong-call-live"><i /> LIVE</span>
            <button
              type="button"
              className="strong-call-minimize"
              aria-label="Minimize call"
              onClick={() => setMinimized(true)}
            >
              −
            </button>
          </div>
        </div>

        <div className="strong-call-body">
          <div className="strong-call-identity">
            <div className="strong-call-avatar">🎙️</div>
            <div>
              <span>CALLING</span>
              <h2>{businessName}</h2>
              <p>AI Reception • Knowledge Brain</p>
            </div>
          </div>

          <div className="strong-call-features">
            <span>● AI listening</span>
            <span>● Live transcript</span>
            <span>● Human handoff</span>
          </div>

          <VoiceCallModal
            slug={slug}
            businessName={businessName}
            existingCustomerId={existingCustomerId}
            agentGender={agentGender}
            onCustomerIdentified={onCustomerIdentified}
            onClose={onClose}
          />
        </div>
      </div>

      {minimized && (
        <button
          type="button"
          className="strong-call-dock"
          onClick={() => setMinimized(false)}
          aria-label="Restore call"
        >
          <span className="strong-call-dock-icon">☎</span>
          <span>
            <b>{businessName}</b>
            <small>Call in progress • Tap to restore</small>
          </span>
          <strong>↗</strong>
        </button>
      )}

      <style jsx>{`
        .strong-call-shell{
          position:fixed;
          inset:0;
          z-index:9998;
          background:
            radial-gradient(circle at 50% 8%,rgba(38,112,82,.42),transparent 34%),
            linear-gradient(145deg,#03110d 0%,#071d16 48%,#020807 100%);
          color:#f5fbf7;
          overflow:auto;
          font-family:inherit;
        }
        .strong-call-shell.is-minimized{
          opacity:0;
          pointer-events:none;
        }
        .strong-call-header{
          height:72px;
          padding:0 24px;
          display:flex;
          align-items:center;
          justify-content:space-between;
          border-bottom:1px solid rgba(255,255,255,.09);
          background:rgba(2,10,8,.74);
          backdrop-filter:blur(18px);
        }
        .strong-call-brand,.strong-call-meta,.strong-call-identity{
          display:flex;
          align-items:center;
        }
        .strong-call-brand{gap:11px}
        .strong-call-logo{
          width:38px;height:38px;border-radius:12px;
          display:grid;place-items:center;
          background:#1d7352;color:#fff;font-weight:900;
          box-shadow:0 8px 24px rgba(29,115,82,.32);
        }
        .strong-call-brand strong{display:block;font-size:13px;letter-spacing:.08em}
        .strong-call-brand span{
          display:block;margin-top:2px;font-size:10px;
          letter-spacing:.12em;color:#91afa3
        }
        .strong-call-meta{gap:12px}
        .strong-call-live{
          display:flex;align-items:center;gap:6px;
          font-size:11px;font-weight:800;letter-spacing:.1em;color:#a7d6bd
        }
        .strong-call-live i{
          width:7px;height:7px;border-radius:50%;
          background:#53d98f;box-shadow:0 0 12px #53d98f
        }
        .strong-call-minimize{
          width:38px;height:38px;border-radius:11px;
          border:1px solid rgba(255,255,255,.13);
          background:rgba(255,255,255,.07);color:#fff;
          font-size:25px;line-height:1;cursor:pointer
        }
        .strong-call-body{
          width:min(760px,calc(100% - 28px));
          margin:26px auto 100px;
          position:relative;
        }
        .strong-call-identity{
          gap:15px;padding:18px 20px;
          border:1px solid rgba(255,255,255,.09);
          border-radius:22px;
          background:rgba(255,255,255,.045);
          box-shadow:0 18px 50px rgba(0,0,0,.22);
        }
        .strong-call-avatar{
          width:54px;height:54px;border-radius:17px;
          display:grid;place-items:center;font-size:24px;
          background:rgba(91,193,148,.16);
          border:1px solid rgba(91,193,148,.25)
        }
        .strong-call-identity span{font-size:10px;letter-spacing:.13em;color:#8eafa1;font-weight:800}
        .strong-call-identity h2{margin:3px 0;font-size:24px}
        .strong-call-identity p{margin:0;color:#9ab0a7;font-size:13px}
        .strong-call-features{
          display:flex;gap:8px;flex-wrap:wrap;
          margin:14px 0 0;
          justify-content:center;
        }
        .strong-call-features span{
          padding:7px 11px;border-radius:999px;
          background:rgba(255,255,255,.055);
          border:1px solid rgba(255,255,255,.08);
          color:#a9c1b7;font-size:11px
        }
        .strong-call-body :global(.vcm-backdrop){
          position:relative!important;
          inset:auto!important;
          z-index:1!important;
          padding:18px 0 0!important;
          background:transparent!important;
          backdrop-filter:none!important;
          display:block!important;
        }
        .strong-call-body :global(.vcm-card){
          max-width:none!important;
          max-height:none!important;
          overflow:visible!important;
          border-radius:24px!important;
          background:rgba(247,251,248,.98)!important;
          box-shadow:0 24px 70px rgba(0,0,0,.35)!important;
        }
        .strong-call-body :global(.vcm-close){display:none!important}
        .strong-call-dock{
          position:fixed;right:18px;bottom:18px;z-index:10050;
          min-width:290px;display:flex;align-items:center;gap:12px;
          padding:12px 14px;border-radius:18px;
          border:1px solid rgba(255,255,255,.12);
          background:rgba(4,19,14,.96);color:#fff;
          box-shadow:0 18px 50px rgba(0,0,0,.42);
          cursor:pointer;text-align:left
        }
        .strong-call-dock-icon{
          width:42px;height:42px;border-radius:13px;
          display:grid;place-items:center;background:#1d7352
        }
        .strong-call-dock b,.strong-call-dock small{display:block}
        .strong-call-dock b{font-size:13px}
        .strong-call-dock small{margin-top:2px;color:#9bb4a9;font-size:11px}
        .strong-call-dock>strong{margin-left:auto;color:#8ed0b0;font-size:20px}
        @media(max-width:600px){
          .strong-call-header{height:62px;padding:0 14px}
          .strong-call-body{width:calc(100% - 18px);margin:12px auto 80px}
          .strong-call-identity{padding:14px}
          .strong-call-identity h2{font-size:20px}
          .strong-call-features{justify-content:flex-start}
          .strong-call-dock{left:10px;right:10px;bottom:10px;min-width:0}
        }
      `}</style>
    </>
  );
}
