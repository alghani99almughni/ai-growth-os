package com.aigrowthos.reception.webrtc

import android.content.Context
import android.media.AudioManager
import android.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.webrtc.AudioSource
import org.webrtc.AudioTrack
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription

class WebRtcConnectionManager(
    private val context: Context,
    private val scope: CoroutineScope,
    private val signaling: WebRtcSignalingManager,
    private val onStateChanged: (WebRtcCallSession) -> Unit = {}
) {
    private val tag = "WebRtcConnection"
    private val _currentCall = MutableStateFlow<WebRtcCallSession?>(null)
    val currentCall: StateFlow<WebRtcCallSession?> = _currentCall.asStateFlow()
    private var factory: PeerConnectionFactory? = null
    private var peer: PeerConnection? = null
    private var audioSource: AudioSource? = null
    private var audioTrack: AudioTrack? = null
    private var durationJob: Job? = null
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    init {
        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(context.applicationContext)
                .setEnableInternalTracer(false).createInitializationOptions()
        )
        factory = PeerConnectionFactory.builder().createPeerConnectionFactory()
    }

    fun startIncomingCall(callId: String, tenantId: String, callerName: String, accessToken: String, apiBaseUrl: String) {
        _currentCall.value = WebRtcCallSession(callId = callId, tenantId = tenantId, callerName = callerName, callState = CallState.RINGING)
        emit()
        signaling.connect(apiBaseUrl, callId, accessToken)
    }

    fun acceptCall() {
        val call = _currentCall.value ?: return
        if (call.callState != CallState.RINGING) return
        setState(call.copy(callState = CallState.CONNECTING))
        audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
        audioManager.isSpeakerphoneOn = true

        val f = factory ?: return fail("WebRTC factory unavailable")
        audioSource = f.createAudioSource(MediaConstraints())
        audioTrack = f.createAudioTrack("local-audio", audioSource)
        audioTrack?.setEnabled(true)

        val servers = listOf(PeerConnection.IceServer.builder("stun:stun.l.google.com:19302").createIceServer())
        val config = PeerConnection.RTCConfiguration(servers).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
        }

        peer = f.createPeerConnection(config, object : PeerConnection.Observer {
            override fun onIceCandidate(c: IceCandidate) {
                signaling.sendIceCandidate(c.sdpMid, c.sdpMLineIndex, c.sdp)
                _currentCall.value?.let { setState(it.copy(iceCandidateCount = it.iceCandidateCount + 1)) }
            }
            override fun onTrack(t: PeerConnection.RtpTransceiver?) {
                val track = t?.receiver?.track()
                if (track is AudioTrack) track.setEnabled(true)
            }
            override fun onAddTrack(r: PeerConnection.RtpReceiver, streams: Array<out org.webrtc.MediaStream>) {
                val track = r.track()
                if (track is AudioTrack) track.setEnabled(true)
            }
            override fun onConnectionChange(s: PeerConnection.PeerConnectionState) {
                when (s) {
                    PeerConnection.PeerConnectionState.CONNECTED -> setState(_currentCall.value?.copy(callState = CallState.CONNECTED))
                    PeerConnection.PeerConnectionState.DISCONNECTED -> fail("WebRTC disconnected")
                    PeerConnection.PeerConnectionState.FAILED -> fail("WebRTC failed")
                    PeerConnection.PeerConnectionState.CLOSED -> endCall(false)
                    else -> Unit
                }
            }
            override fun onIceConnectionChange(s: PeerConnection.IceConnectionState) {
                if (s == PeerConnection.IceConnectionState.FAILED) fail("ICE failed")
            }
            override fun onAddStream(stream: org.webrtc.MediaStream) = Unit
            override fun onIceConnectionReceivingChange(receiving: Boolean) = Unit
            override fun onIceGatheringChange(s: PeerConnection.IceGatheringState) = Unit
            override fun onIceCandidatesRemoved(candidates: Array<out IceCandidate>) = Unit
            override fun onSignalingChange(s: PeerConnection.SignalingState) = Unit
            override fun onRemoveStream(stream: org.webrtc.MediaStream) = Unit
            override fun onDataChannel(channel: org.webrtc.DataChannel) = Unit
            override fun onRenegotiationNeeded() = Unit
        }) ?: return fail("Could not create PeerConnection")

        peer?.addTrack(audioTrack)
        startDurationTimer()
    }

    fun handleOffer(sdp: String) {
        val pc = peer ?: return fail("PeerConnection is not ready")
        pc.setRemoteDescription(SimpleSdpObserver(), SessionDescription(SessionDescription.Type.OFFER, sdp))
        pc.createAnswer(object : SdpObserver {
            override fun onCreateSuccess(d: SessionDescription) {
                pc.setLocalDescription(SimpleSdpObserver(), d)
                signaling.sendAnswer(d.description)
                setState(_currentCall.value?.copy(localSdp = d.description, remoteSdp = sdp, callState = CallState.CONNECTING))
            }
            override fun onSetSuccess() = Unit
            override fun onCreateFailure(error: String) = fail(error)
            override fun onSetFailure(error: String) = fail(error)
        }, MediaConstraints())
    }

    fun handleIceCandidate(event: SignalEvent.IceCandidate) {
        peer?.addIceCandidate(IceCandidate(event.sdpMid, event.sdpMLineIndex, event.candidate))
    }

    fun toggleMute(): Boolean {
        val track = audioTrack ?: return false
        val wasEnabled = track.enabled()
        track.setEnabled(!wasEnabled)
        _currentCall.value?.let { setState(it.copy(isMicMuted = wasEnabled)) }
        return wasEnabled
    }

    fun toggleHold(): Boolean {
        val call = _currentCall.value ?: return false
        val held = call.callState != CallState.ON_HOLD
        audioTrack?.setEnabled(!held)
        signaling.sendHold(held)
        setState(call.copy(callState = if (held) CallState.ON_HOLD else CallState.CONNECTED))
        return held
    }

    fun endCall(notifyPeer: Boolean = true): WebRtcCallSession? {
        val call = _currentCall.value ?: return null
        if (notifyPeer) signaling.sendHangup()
        durationJob?.cancel()
        peer?.close()
        peer = null
        audioTrack?.dispose()
        audioTrack = null
        audioSource?.dispose()
        audioSource = null
        signaling.disconnect()
        audioManager.mode = AudioManager.MODE_NORMAL
        audioManager.isSpeakerphoneOn = false
        val ended = call.copy(callState = CallState.ENDED)
        _currentCall.value = ended
        onStateChanged(ended)
        return ended
    }

    fun release() {
        endCall(false)
        factory?.dispose()
        factory = null
    }

    private fun startDurationTimer() {
        durationJob?.cancel()
        durationJob = scope.launch {
            var seconds = 0
            while (isActive && _currentCall.value?.callState == CallState.CONNECTED) {
                delay(1000)
                seconds++
                _currentCall.value?.let { setState(it.copy(callDurationSec = seconds)) }
            }
        }
    }

    private fun setState(call: WebRtcCallSession?) {
        _currentCall.value = call
        if (call != null) onStateChanged(call)
    }
    private fun emit() = _currentCall.value?.let(onStateChanged)
    private fun fail(message: String) {
        Log.e(tag, message)
        _currentCall.value?.let { setState(it.copy(callState = CallState.FAILED, lastError = message)) }
    }
    private class SimpleSdpObserver : SdpObserver {
        override fun onCreateSuccess(d: SessionDescription) = Unit
        override fun onSetSuccess() = Unit
        override fun onCreateFailure(error: String) = Unit
        override fun onSetFailure(error: String) = Unit
    }
}
