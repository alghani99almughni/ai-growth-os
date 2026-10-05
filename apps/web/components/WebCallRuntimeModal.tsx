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
 * Pilot Web Call Runtime.
 *
 * First-tenant runtime intentionally reuses the proven VoiceCallModal
 * orchestration so the existing library-first Knowledge Brain, booking,
 * CRM, escalation and browser TTS remain the source of truth.
 *
 * The raw Gemini PCM WebSocket runtime is not used for this pilot until it
 * passes the same end-to-end contract as the proven path.
 */
export default function WebCallRuntimeModal({
  onClose,
  slug,
  businessName,
  existingCustomerId,
  agentGender="female",
  onCustomerIdentified,
}:Props){
  return (
    <VoiceCallModal
      slug={slug || "ss-nutritions"}
      businessName={businessName || "SS Nutritions"}
      existingCustomerId={existingCustomerId}
      agentGender={agentGender}
      onCustomerIdentified={onCustomerIdentified}
      onClose={onClose}
    />
  );
}
