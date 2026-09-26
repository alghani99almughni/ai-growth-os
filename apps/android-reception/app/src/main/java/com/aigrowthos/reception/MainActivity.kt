package com.aigrowthos.reception
import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.text.InputType
import android.widget.*
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*
class MainActivity:ComponentActivity(){
 private val scope=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
 private var auth:AuthSession?=null;private var manager:WebRtcSignalingManager?=null;private var pollJob:Job?=null
 private lateinit var status:TextView;private lateinit var calls:LinearLayout;private lateinit var apiInput:EditText;private lateinit var emailInput:EditText;private lateinit var passwordInput:EditText
 private val micPermission=registerForActivityResult(ActivityResultContracts.RequestPermission()){if(!it)status.text="Microphone permission is required."}
 override fun onCreate(state:Bundle?){super.onCreate(state);buildUi();if(ContextCompat.checkSelfPermission(this,Manifest.permission.RECORD_AUDIO)!=PackageManager.PERMISSION_GRANTED)micPermission.launch(Manifest.permission.RECORD_AUDIO)}
 private fun buildUi(){
  val root=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(32,32,32,32)}
  apiInput=EditText(this).apply{hint="API URL";setText("https://your-api.onrender.com")}
  emailInput=EditText(this).apply{hint="Staff email"}
  passwordInput=EditText(this).apply{hint="Password";inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD}
  val login=Button(this).apply{text="Sign in to Reception"};status=TextView(this).apply{text="Offline";textSize=16f};calls=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL}
  root.addView(apiInput);root.addView(emailInput);root.addView(passwordInput);root.addView(login);root.addView(status);root.addView(TextView(this).apply{text="Incoming calls";textSize=20f;setPadding(0,24,0,12)});root.addView(calls);setContentView(ScrollView(this).apply{addView(root)});login.setOnClickListener{signIn()}
 }
 private fun signIn(){val api=ApiClient(apiInput.text.toString().trim().trimEnd('/'));status.text="Signing in…";scope.launch{try{auth=api.login(emailInput.text.toString().trim(),passwordInput.text.toString());status.text="Online as "+auth!!.userName;startPolling(api)}catch(t:Throwable){status.text=t.message?:"Login failed"}}}
 private fun startPolling(api:ApiClient){pollJob?.cancel();pollJob=scope.launch{while(isActive){try{auth?.let{renderCalls(api,it,api.calls(it))}}catch(t:Throwable){status.text="Polling error: "+(t.message?:"unknown")};delay(3000)}}}
 private fun renderCalls(api:ApiClient,s:AuthSession,pending:List<PendingCall>){calls.removeAllViews();if(pending.isEmpty()){calls.addView(TextView(this).apply{text="No calls waiting."});return};pending.forEach{call->val row=LinearLayout(this).apply{orientation=LinearLayout.VERTICAL;setPadding(0,16,0,16)};row.addView(TextView(this).apply{text="☎ "+call.customerName+" • "+call.status});val actions=LinearLayout(this);val accept=Button(this).apply{text="Answer"};val decline=Button(this).apply{text="Decline"};actions.addView(accept);actions.addView(decline);row.addView(actions);calls.addView(row);accept.setOnClickListener{acceptCall(api,s,call)};decline.setOnClickListener{scope.launch{runCatching{api.handoffDecision(s,call.id,false)}}}}
 }
 private fun acceptCall(api:ApiClient,s:AuthSession,call:PendingCall){status.text="Accepting…";scope.launch{try{api.handoffDecision(s,call.id,true);val m=WebRtcSignalingManager(this@MainActivity,apiInput.text.toString().trim().trimEnd('/'),s.token,call.id,s.tenantId,api.iceServers("ss-nutritions"),onConnected={runOnUiThread{status.text="Connected to "+call.customerName}},onEnded={runOnUiThread{status.text="Call ended"};scope.launch{runCatching{api.staffRelease(s,call.id)}}});manager?.close();manager=m;m.connectAndOffer();status.text="Connecting to "+call.customerName+"…"}catch(t:Throwable){status.text=t.message?:"Unable to answer"}}}
 override fun onDestroy(){pollJob?.cancel();manager?.close();scope.cancel();super.onDestroy()}
}
