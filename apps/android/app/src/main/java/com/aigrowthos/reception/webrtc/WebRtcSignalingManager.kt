package com.aigrowthos.reception.webrtc

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.net.URLEncoder
import java.util.concurrent.TimeUnit

sealed interface SignalEvent {
    data class Offer(val sdp: String) : SignalEvent
    data class Answer(val sdp: String) : SignalEvent
    data class IceCandidate(val sdpMid: String?, val sdpMLineIndex: Int, val candidate: String) : SignalEvent
    data object PeerJoined : SignalEvent
    data object PeerLeft : SignalEvent
    data class Error(val message: String) : SignalEvent
}

class WebRtcSignalingManager(
    private val client: OkHttpClient = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()
) {
    private val tag = "WebRtcSignaling"
    private val _wsConnected = MutableStateFlow(false)
    val wsConnected: StateFlow<Boolean> = _wsConnected.asStateFlow()
    private val _events = MutableStateFlow<SignalEvent?>(null)
    val events: StateFlow<SignalEvent?> = _events.asStateFlow()
    private var socket: WebSocket? = null

    fun connect(apiBaseUrl: String, callId: String, accessToken: String, onConnected: () -> Unit = {}) {
        disconnect()
        val wsBase = apiBaseUrl.trimEnd('/')
            .replaceFirst("https://", "wss://")
            .replaceFirst("http://", "ws://")
        val url = wsBase + "/ws/calls/" + encode(callId) + "?access_token=" + encode(accessToken)
        socket = client.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                _wsConnected.value = true
                send(JSONObject().put("type", "staff_join"))
                onConnected()
            }
            override fun onMessage(webSocket: WebSocket, text: String) = handleIncoming(text)
            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { _wsConnected.value = false }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) { _wsConnected.value = false }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                _wsConnected.value = false
                _events.value = SignalEvent.Error(t.message ?: "WebSocket signaling failed")
                Log.e(tag, "WebSocket failure", t)
            }
        })
    }

    fun sendOffer(sdp: String) = send(JSONObject().put("type", "offer").put("sdp", sdp))
    fun sendAnswer(sdp: String) = send(JSONObject().put("type", "answer").put("sdp", sdp))
    fun sendIceCandidate(mid: String?, index: Int, candidate: String) =
        send(JSONObject().put("type", "ice_candidate").put("sdpMid", mid ?: JSONObject.NULL)
            .put("sdpMLineIndex", index).put("candidate", candidate))
    fun sendHangup() = send(JSONObject().put("type", "hangup"))
    fun sendHold(held: Boolean) = send(JSONObject().put("type", "hold").put("held", held))

    fun disconnect() {
        socket?.close(1000, "client disconnect")
        socket = null
        _wsConnected.value = false
    }

    private fun send(message: JSONObject): Boolean = socket?.send(message.toString()) == true

    private fun handleIncoming(raw: String) {
        try {
            val json = JSONObject(raw)
            when (json.optString("type")) {
                "offer" -> _events.value = SignalEvent.Offer(json.optString("sdp"))
                "answer" -> _events.value = SignalEvent.Answer(json.optString("sdp"))
                "ice_candidate" -> _events.value = SignalEvent.IceCandidate(
                    if (json.isNull("sdpMid")) null else json.optString("sdpMid"),
                    json.optInt("sdpMLineIndex"),
                    json.optString("candidate")
                )
                "peer_joined" -> _events.value = SignalEvent.PeerJoined
                "peer_left", "hangup" -> _events.value = SignalEvent.PeerLeft
                "error" -> _events.value = SignalEvent.Error(json.optString("message", "Signaling error"))
            }
        } catch (t: Throwable) {
            _events.value = SignalEvent.Error("Invalid signaling message")
            Log.w(tag, "Invalid signaling payload", t)
        }
    }

    private fun encode(value: String) = URLEncoder.encode(value, Charsets.UTF_8.name())
}
