package com.aigrowthos.reception.webrtc

import org.junit.Assert.assertEquals
import org.junit.Test

class WebRtcCallSessionTest {
    @Test
    fun auraLifecycleStateModelIsPreserved() {
        val session = WebRtcCallSession(callId = "call-1", tenantId = "tenant-1", callerName = "Customer")
        assertEquals(CallState.IDLE, session.callState)
        assertEquals("call-1", session.callId)
        assertEquals("tenant-1", session.tenantId)
    }
}
