"use client";

import VoiceCallModal from "./VoiceCallModal";

type Props = {
  slug:string;
  businessName:string;
  existingCustomerId?:string|null;
  agentGender?:"male"|"female";
  onCustomerIdentified?:(customerId:string)=>void;
  onClose:()=>void;
};

/** Production pilot entry point for the browser Web Call Runtime. */
export default function WebCallRuntimeModal(props:Props) {
  return <VoiceCallModal {...props} />;
}
