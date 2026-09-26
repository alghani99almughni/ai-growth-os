package com.aigrowthos.reception
import java.util.UUID
enum class CallState { IDLE, RINGING, CONNECTING, CONNECTED, ON_HOLD, ENDED, FAILED }
data class WebRtcCallSession(
    val sessionId: String = UUID.randomUUID().toString(),
    val callId: String,
    val tenantId: String,
    val customerName: String = "",
    val state: CallState = CallState.IDLE,
    val remoteSdpSet: Boolean = false,
    val localSdpSet: Boolean = false,
    val iceCandidates: Int = 0,
    val muted: Boolean = false,
    val error: String? = null
)
