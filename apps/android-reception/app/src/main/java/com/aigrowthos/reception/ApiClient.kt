package com.aigrowthos.reception
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.*
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit
data class AuthSession(val token:String,val tenantId:String,val userId:String,val userName:String)
data class PendingCall(val id:String,val tenantId:String,val customerName:String,val status:String,val staffId:String?)
class ApiClient(private val baseUrl:String){
 private val http=OkHttpClient.Builder().connectTimeout(10,TimeUnit.SECONDS).readTimeout(15,TimeUnit.SECONDS).build()
 private val json="application/json".toMediaType()
 suspend fun login(email:String,password:String)=withContext(Dispatchers.IO){
  val body=JSONObject().put("email",email).put("password",password).toString().toRequestBody(json)
  http.newCall(Request.Builder().url(baseUrl+"/api/v1/auth/login").post(body).build()).execute().use{r->
   val text=r.body?.string().orEmpty();if(!r.isSuccessful)error(JSONObject(text).optString("detail","Login failed"));val o=JSONObject(text)
   AuthSession(o.getString("access_token"),o.getJSONObject("tenant").getString("id"),o.getJSONObject("user").getString("id"),o.getJSONObject("user").optString("name",email))
  }
 }
 suspend fun calls(s:AuthSession)=withContext(Dispatchers.IO){
  val req=Request.Builder().url(baseUrl+"/api/v1/tenants/"+s.tenantId+"/calls").header("Authorization","Bearer "+s.token).get().build()
  http.newCall(req).execute().use{r->if(!r.isSuccessful)return@withContext emptyList();val arr=JSONObject(r.body?.string().orEmpty()).optJSONArray("items")?:JSONArray();buildList{for(i in 0 until arr.length()){val o=arr.getJSONObject(i);val st=o.optString("status");if(st=="handoff_requested"||st=="ringing")add(PendingCall(o.getString("id"),s.tenantId,o.optString("customer_name","Customer"),st,o.optString("staff_id").takeIf{it.isNotBlank()}))}}}
 }
 suspend fun handoffDecision(s:AuthSession,id:String,accept:Boolean)=withContext(Dispatchers.IO){
  val body=JSONObject().put("decision",if(accept)"accept" else "decline").toString().toRequestBody(json)
  http.newCall(Request.Builder().url(baseUrl+"/api/v1/tenants/"+s.tenantId+"/calls/"+id+"/handoff/decision").header("Authorization","Bearer "+s.token).post(body).build()).execute().use{r->val text=r.body?.string().orEmpty();if(!r.isSuccessful)error(JSONObject(text).optString("detail","Unable to update call"));JSONObject(text)}
 }
 suspend fun iceServers(slug:String)=withContext(Dispatchers.IO){
  val fallback=listOf(org.webrtc.PeerConnection.IceServer.builder("stun:stun.l.google.com:19302").createIceServer())
  val req=Request.Builder().url(baseUrl+"/api/v1/public/business/"+slug+"/voice/ice").get().build()
  http.newCall(req).execute().use{r->if(!r.isSuccessful)return@withContext fallback;val arr=JSONObject(r.body?.string().orEmpty()).optJSONArray("ice_servers")?:JSONArray();buildList{for(i in 0 until arr.length()){val o=arr.getJSONObject(i);val b=org.webrtc.PeerConnection.IceServer.builder(o.getString("urls"));if(o.has("username"))b.setUsername(o.optString("username"));if(o.has("credential"))b.setPassword(o.optString("credential"));add(b.createIceServer())}}}
 }
}
