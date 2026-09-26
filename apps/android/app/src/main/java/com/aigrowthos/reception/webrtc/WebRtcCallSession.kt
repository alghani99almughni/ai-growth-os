package com.aigrowthos.reception.webrtc

import java.util.UUID

enum class CallState { IDLE, RINGING, CONNECTING, CONNECTED, ON_HOLD, ROUTED, ENDED, FAILED }

data class WebRtcCallSession(
    val sessionId: String = UUID.randomUUID().toString(),
    val callId: String = "",
    val tenantId: String = "",
    val callerName: String = "PWA Customer",
    val callerDevice: String = "Web PWA",
    val callState: CallState = CallState.IDLE,
    val callDurationSec: Int = 0,
    val localSdp: String = "",
    val remoteSdp: String = "",
    val iceCandidateCount: Int = 0,
    val isMicMuted: Boolean = false,
    val targetHost: String = "",
    val targetDepartment: String = "",
    val lastError: String? = null
)
