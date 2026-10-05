"use client";

import VoiceCallModal from "./VoiceCallModal";

type Props={
  onClose:()=>void;
  slug?:string;
  businessName?:string;
  existingCustomerId?:string;
  agentGender?:"male"|"female";
  onCustomerIdentified?:(customerId:string)=>void;
};

/**
 * Production web-call entry point.
 *
 * IMPORTANT: this is only a presentation shell. The proven four-layer
 * VoiceCallModal remains the actual call engine:
 *   1) Knowledge Brain
 *   2) Specialist AI (opt-in; currently OFF)
 *   3) Human WebRTC
 *   4) Callback
 *
 * The raw Gemini Live browser runtime is intentionally not used.
 */
export default function WebCallRuntimeModal({
  onClose,
  slug="ss-nutritions",
  businessName="SS Nutritions",
  existingCustomerId,
  agentGender="female",
  onCustomerIdentified,
}:Props){
  return (
    <div className="new-call-shell">
      <div className="new-call-topline">
        <div>
          <span className="new-call-brand">AI GROWTH OS</span>
          <span className="new-call-secure">SECURE WEB CALL</span>
        </div>
        <span className="new-call-live-dot" aria-label="Call service ready" />
      </div>

      <VoiceCallModal
        slug={slug}
        businessName={businessName}
        existingCustomerId={existingCustomerId}
        agentGender={agentGender}
        onCustomerIdentified={onCustomerIdentified}
        onClose={onClose}
      />

      <style jsx>{`
        .new-call-shell{position:fixed;inset:0;z-index:9999;background:radial-gradient(circle at 50% 15%,#173d32 0,#071712 42%,#030908 100%);color:#fff;overflow:auto}
        .new-call-topline{position:fixed;top:0;left:0;right:0;z-index:10001;height:64px;padding:0 28px;display:flex;align-items:center;justify-content:space-between;box-sizing:border-box;background:rgba(3,9,8,.72);backdrop-filter:blur(16px);border-bottom:1px solid rgba(255,255,255,.09)}
        .new-call-brand{font-size:13px;font-weight:800;letter-spacing:.16em}
        .new-call-secure{margin-left:12px;font-size:11px;letter-spacing:.12em;color:#a9c8bb}
        .new-call-live-dot{width:9px;height:9px;border-radius:50%;background:#62d5a5;box-shadow:0 0 18px rgba(98,213,165,.85)}
        .new-call-shell :global(.vcm-backdrop){position:static;inset:auto;min-height:100%;padding:92px 20px 34px;background:transparent;backdrop-filter:none;align-items:flex-start}
        .new-call-shell :global(.vcm-card){max-width:520px;border-radius:30px;background:rgba(247,251,249,.98);box-shadow:0 30px 90px rgba(0,0,0,.42);padding:32px 28px;color:#0b3326}
        .new-call-shell :global(.vcm-title){font-size:34px;letter-spacing:-.035em}
        .new-call-shell :global(.vcm-sub){font-size:15px}
        .new-call-shell :global(.vcm-primary){background:#17664b;box-shadow:0 10px 25px rgba(23,102,75,.2)}
        .new-call-shell :global(.vcm-pulse){width:104px;height:104px;background:#e0f1e9}
        .new-call-shell :global(.vcm-transcript){min-height:130px;max-height:280px}
        .new-call-shell :global(.vcm-close){display:none}
        @media (max-width:640px){
          .new-call-topline{padding:0 16px}
          .new-call-secure{display:none}
          .new-call-shell :global(.vcm-backdrop){padding:78px 12px 20px}
          .new-call-shell :global(.vcm-card){padding:26px 18px;border-radius:24px}
          .new-call-shell :global(.vcm-title){font-size:29px}
        }
      `}</style>
    </div>
  );
}
