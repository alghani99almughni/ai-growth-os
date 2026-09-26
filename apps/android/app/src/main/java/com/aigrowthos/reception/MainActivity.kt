package com.aigrowthos.reception

import android.Manifest
import androidx.activity.ComponentActivity
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.result.contract.ActivityResultContracts
import com.aigrowthos.reception.webrtc.ReceptionWebRtcController
import com.aigrowthos.reception.webrtc.WebRtcConnectionManager
import com.aigrowthos.reception.webrtc.WebRtcSignalingManager
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.collectLatest
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private lateinit var controller: ReceptionWebRtcController
    private lateinit var status: TextView

    private val micPermission = registerForActivityResult(
        ActivityResultContracts.RequestPermission()
    ) { granted ->
        status.text = if (granted) "Microphone ready" else "Microphone permission required"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val signaling = WebRtcSignalingManager()
        val connection = WebRtcConnectionManager(this, scope, signaling)
        controller = ReceptionWebRtcController(scope, signaling, connection)

        status = TextView(this).apply {
            text = "AI Growth OS Reception • WebRTC ready"
            textSize = 18f
            setPadding(32, 48, 32, 32)
        }
        val requestMic = Button(this).apply {
            text = "Enable microphone"
            setOnClickListener { micPermission.launch(Manifest.permission.RECORD_AUDIO) }
        }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            addView(status)
            addView(requestMic)
        })
        scope.launch {
            controller.currentCall.collectLatest { call ->
                status.text = when {
                    call == null -> "Ready for incoming call"
                    call.lastError != null -> "Call error: " + call.lastError
                    else -> "Call " + call.callState + " • " + call.callerName
                }
            }
        }
    }

    override fun onDestroy() {
        controller.stop()
        scope.cancel()
        super.onDestroy()
    }
}
