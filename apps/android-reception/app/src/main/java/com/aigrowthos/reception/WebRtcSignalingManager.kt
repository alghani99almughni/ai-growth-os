package com.aigrowthos.reception
import android.content.Context
import android.media.AudioManager
import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.*
import org.json.JSONObject
import org.webrtc.*
import org.webrtc.audio.JavaAudioDeviceModule
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

class WebRtcSignalingManager(
    private val context: Context,
    private val apiBaseUrl: String,
    private val accessToken: String,
    private val callId: String,
    private val tenantId: String,
    private val iceServers: List<PeerConnection.IceServer>,
    private val onConnected: () -> Unit = {},
    private val onEnded: () -> Unit = {}
) {
    private val client = OkHttpClient.Builder().pingInterval(20, TimeUnit.SECONDS).retryOnConnectionFailure(true).build()
    private val _session = MutableStateFlow(WebRtcCallSession(callId = callId, tenantId = tenantId, state = CallState.RINGING))
    val session: StateFlow<WebRtcCallSession> = _session.asStateFlow()
    private var socket: WebSocket? = null
    private var factory: PeerConnectionFactory? = null
    private var peer: PeerConnection? = null
    private var audioSource: AudioSource? = null
    private var audioTrack: AudioTrack? = null
    private var audioModule: JavaAudioDeviceModule? = null

    fun connectAndOffer() {
        try { initializeFactory(); createPeer(); socket = client.newWebSocket(Request.Builder().url(wsUrl()).build(), SignalListener()); transition(CallState.CONNECTING) }
        catch (t: Throwable) { fail(t.message ?: "WebRTC initialization failed") }
    }
    private fun initializeFactory() {
        if (factory != null) return
        PeerConnectionFactory.initialize(PeerConnectionFactory.InitializationOptions.builder(context).createInitializationOptions())
        audioModule = JavaAudioDeviceModule.builder(context).setUseHardwareAcousticEchoCanceler(true).setUseHardwareNoiseSuppressor(true).createAudioDeviceModule()
        factory = PeerConnectionFactory.builder().setAudioDeviceModule(audioModule).createPeerConnectionFactory()
        val am = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        am.mode = AudioManager.MODE_IN_COMMUNICATION; am.isSpeakerphoneOn = true
    }
    private fun createPeer() {
        val f = factory ?: error("PeerConnectionFactory unavailable")
        val config = PeerConnection.RTCConfiguration(iceServers).apply { sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN; bundlePolicy = PeerConnection.BundlePolicy.MAXBUNDLE; rtcpMuxPolicy = PeerConnection.RtcpMuxPolicy.REQUIRE }
        peer = f.createPeerConnection(config, object : PeerConnection.Observer {
            override fun onIceCandidate(c: IceCandidate) { send(JSONObject().put("type","ice-candidate").put("candidate",JSONObject().put("sdpMid",c.sdpMid).put("sdpMLineIndex",c.sdpMLineIndex).put("candidate",c.sdp))); _session.value = _session.value.copy(iceCandidates = _session.value.iceCandidates + 1) }
            override fun onIceCandidatesRemoved(c: Array<out IceCandidate>) = Unit
            override fun onSignalingChange(s: PeerConnection.SignalingState) = Unit
            override fun onIceConnectionChange(s: PeerConnection.IceConnectionState) {
                if (s == PeerConnection.IceConnectionState.CONNECTED || s == PeerConnection.IceConnectionState.COMPLETED) { transition(CallState.CONNECTED); onConnected() }
                if (s == PeerConnection.IceConnectionState.FAILED) fail("ICE connection failed")
            }
            override fun onConnectionChange(s: PeerConnection.PeerConnectionState) {
                if (s == PeerConnection.PeerConnectionState.CONNECTED) { transition(CallState.CONNECTED); onConnected() }
                if (s == PeerConnection.PeerConnectionState.FAILED) fail("Peer connection failed")
                if (s == PeerConnection.PeerConnectionState.CLOSED) onEnded()
            }
            override fun onIceConnectionReceivingChange(b: Boolean) = Unit
            override fun onIceGatheringChange(s: PeerConnection.IceGatheringState) = Unit
            override fun onAddStream(stream: MediaStream) { stream.audioTracks.forEach { it.setEnabled(true) } }
            override fun onRemoveStream(stream: MediaStream) = Unit
            override fun onDataChannel(c: DataChannel) = Unit
            override fun onRenegotiationNeeded() = Unit
            override fun onAddTrack(receiver: RtpReceiver, streams: Array<out MediaStream>) { (receiver.track() as? AudioTrack)?.setEnabled(true) }
            override fun onStandardizedIceConnectionChange(s: PeerConnection.IceConnectionState) = Unit
            override fun onSelectedCandidatePairChanged(e: PeerConnection.CandidatePairChangeEvent) = Unit
            override fun onTrack(t: RtpTransceiver) = Unit
        }) ?: error("PeerConnection creation failed")
        val constraints = MediaConstraints().apply { mandatory.add(MediaConstraints.KeyValuePair("googEchoCancellation","true")); mandatory.add(MediaConstraints.KeyValuePair("googNoiseSuppression","true")); mandatory.add(MediaConstraints.KeyValuePair("googAutoGainControl","true")) }
        audioSource = f.createAudioSource(constraints); audioTrack = f.createAudioTrack("reception-audio", audioSource); audioTrack?.setEnabled(true); peer?.addTrack(audioTrack)
    }
    private fun createOffer() {
        val p = peer ?: return
        p.createOffer(object : SdpObserverAdapter() {
            override fun onCreateSuccess(d: SessionDescription) { p.setLocalDescription(SdpObserverAdapter { _session.value = _session.value.copy(localSdpSet = true) }, d); send(JSONObject().put("type","offer").put("sdp",d.description)) }
            override fun onCreateFailure(error: String) { fail("Offer failed: " + error) }
        }, MediaConstraints())
    }
    private fun handleAnswer(sdp: String) { peer?.setRemoteDescription(SdpObserverAdapter { _session.value = _session.value.copy(remoteSdpSet = true) }, SessionDescription(SessionDescription.Type.ANSWER,sdp)) }
    private fun handleCandidate(o: JSONObject) { peer?.addIceCandidate(IceCandidate(if (o.isNull("sdpMid")) null else o.optString("sdpMid"),o.optInt("sdpMLineIndex",0),o.optString("candidate"))); _session.value = _session.value.copy(iceCandidates = _session.value.iceCandidates + 1) }
    private inner class SignalListener : WebSocketListener() {
        override fun onOpen(ws: WebSocket, response: Response) { send(JSONObject().put("type","staff_join").put("call_id",callId)); createOffer() }
        override fun onMessage(ws: WebSocket, text: String) { try { val m=JSONObject(text); when(m.optString("type")) { "answer"->handleAnswer(m.optString("sdp")); "ice-candidate"->handleCandidate(m.optJSONObject("candidate")?:m); "hangup","stop"->{closeInternal(false);onEnded()}; "error"->fail(m.optString("message","Signaling error")) } } catch(t:Throwable){ Log.w("AGOS-WebRTC","Bad signaling message",t) } }
        override fun onFailure(ws: WebSocket,t:Throwable,response:Response?){ fail(t.message ?: "WebSocket failed") }
        override fun onClosed(ws: WebSocket,code:Int,reason:String){ if(_session.value.state!=CallState.ENDED) onEnded() }
    }
    fun setMuted(muted:Boolean){ audioTrack?.setEnabled(!muted); _session.value=_session.value.copy(muted=muted,state=if(muted)CallState.ON_HOLD else CallState.CONNECTED) }
    fun hangUp(){ send(JSONObject().put("type","hangup")); closeInternal(true) }
    fun close(){ closeInternal(true) }
    private fun send(m:JSONObject){ socket?.send(m.toString()) }
    private fun closeInternal(ended:Boolean){ try{socket?.close(1000,"call ended")}catch(_:Throwable){}; socket=null; peer?.close();peer?.dispose();peer=null;audioTrack?.dispose();audioTrack=null;audioSource?.dispose();audioSource=null;audioModule?.release();audioModule=null;factory?.dispose();factory=null;if(ended){_session.value=_session.value.copy(state=CallState.ENDED);onEnded()} }
    private fun transition(s:CallState){_session.value=_session.value.copy(state=s)}
    private fun fail(message:String){_session.value=_session.value.copy(state=CallState.FAILED,error=message);closeInternal(false)}
    private fun wsUrl():String{val base=apiBaseUrl.trimEnd('/').replaceFirst("https://","wss://").replaceFirst("http://","ws://");return base+"/ws/calls/"+callId+"?access_token="+URLEncoder.encode(accessToken,"UTF-8")}
    private open class SdpObserverAdapter(private val success:(()->Unit)?=null):SdpObserver{override fun onCreateSuccess(d:SessionDescription){};override fun onSetSuccess(){success?.invoke()};override fun onCreateFailure(e:String){};override fun onSetFailure(e:String){}}
}
