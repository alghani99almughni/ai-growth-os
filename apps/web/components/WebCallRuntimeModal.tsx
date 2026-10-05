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
 * Keep the existing four-layer VoiceCallModal as the runtime for the pilot:
 *   Layer 1 deterministic Knowledge Brain
 *   Layer 2 optional specialist AI
 *   Layer 3 human WebRTC handoff
 *   Layer 4 callback ticket
 *
 * The raw Gemini Live browser runtime is intentionally not used here.
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
    <VoiceCallModal
      slug={slug}
      businessName={businessName}
      existingCustomerId={existingCustomerId}
      agentGender={agentGender}
      onCustomerIdentified={onCustomerIdentified}
      onClose={onClose}
    />
  );
}
