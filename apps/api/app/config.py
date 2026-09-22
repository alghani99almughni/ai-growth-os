from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name:str="AI Growth OS API"; environment:str="development"
    database_url:str="postgresql+psycopg://growth:growth@localhost:5432/growth_os"; redis_url:str="redis://localhost:6379/0"
    jwt_secret:str="change-me-in-production"; jwt_algorithm:str="HS256"; access_token_minutes:int=1440
    gemini_api_key:str=""; gemini_model:str="gemini-2.5-flash"; openai_api_key:str=""; openai_model:str="gpt-5.6-luna"; openrouter_api_key:str=""; openrouter_model:str="qwen/qwen3-coder"; anthropic_api_key:str=""; anthropic_model:str="claude-3-5-haiku-latest"; gemini_live_model:str="gemini-3.8-live"; public_app_url:str="http://localhost:3000"
    allowed_origins:str="http://localhost:3000"; rate_limit_requests:int=120; rate_limit_window_seconds:int=60
    whatsapp_provider:str="openwa"; whatsapp_welcome_enabled:bool=True; whatsapp_credential_encryption_key:str="" ; integration_credential_encryption_key:str="" ; openwa_base_url:str="http://localhost:2785"; openwa_api_key:str=""; openwa_session_id:str=""; openwa_webhook_secret:str=""; whatsapp_access_token:str=""; whatsapp_phone_number_id:str=""; razorpay_key_id:str=""; razorpay_key_secret:str=""
    turn_url:str=""; turn_username:str=""; turn_credential:str=""
    stt_provider:str="google"; tts_provider:str="google"; stt_api_key:str=""; tts_api_key:str=""
    telephony_provider:str=""; telephony_api_key:str=""; telephony_webhook_secret:str=""
    ai_voice_enabled:bool=False
    meta_client_id:str=""; meta_client_secret:str=""; meta_redirect_uri:str=""
    meta_graph_api_version:str="v23.0"
    google_client_id:str=""; google_client_secret:str=""; google_redirect_uri:str=""
    oauth_state_ttl_seconds:int=600
    platform_admin_email:str=""
    platform_admin_password:str=""
    platform_admin_name:str="Platform Administrator"
    resend_api_key:str=""
    notification_from_email:str=""
    notification_from_name:str="AI Growth OS"
    password_reset_ttl_minutes:int=30
    notification_whatsapp_provider:str=""
    notification_whatsapp_access_token:str=""
    notification_whatsapp_phone_number_id:str=""
    notification_whatsapp_openwa_base_url:str=""
    notification_whatsapp_openwa_api_key:str=""
    notification_whatsapp_openwa_session_id:str=""
    model_config=SettingsConfigDict(env_file=".env",extra="ignore")

settings=Settings()
