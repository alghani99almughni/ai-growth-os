package com.aigrowthos.reception.webrtc

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.launch

class ReceptionWebRtcController(
    private val scope: CoroutineScope,
    private val signaling: WebRtcSignalingManager,
    private val connection: WebRtcConnectionManager
) {
    val currentCall: StateFlow<WebRtcCallSession?> = connection.currentCall
    val signalingConnected: StateFlow<Boolean> = signaling.wsConnected

    private val eventJob: Job = scope.launch {
        var seen: SignalEvent? = null
        while (true) {
            val event = signaling.events.value
            if (event != null && event !== seen) {
                seen = event
                when (event) {
                    is SignalEvent.Offer -> connection.handleOffer(event.sdp)
                    is SignalEvent.IceCandidate -> connection.handleIceCandidate(event)
                    is SignalEvent.PeerLeft -> connection.endCall(false)
                    is SignalEvent.Error -> Unit
                    SignalEvent.Answer, SignalEvent.PeerJoined -> Unit
                }
            }
            delay(50)
        }
    }

    fun accept() = connection.acceptCall()
    fun toggleMute() = connection.toggleMute()
    fun toggleHold() = connection.toggleHold()
    fun end() = connection.endCall()
    fun stop() {
        eventJob.cancel()
        connection.release()
    }
}
