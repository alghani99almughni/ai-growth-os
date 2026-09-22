from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name:str="AI Growth OS API"; environment:str="development"
    database_url:str="postgresql+psycopg://growth:growth@localhost:5432/growth_os"; redis_url:str="redis://localhost:6379/0"
    jwt_secret:str="change-me-in-production"; jwt_algorithm:str="HS256"; access_token_minutes:int=1440
    gemini_api_key:str=""; gemini_model:str="gemini-2.5-flash"; gemini_live_model:str="gemini-3.8-live"; public_app_url:str="http://localhost:3000"
    allowed_origins:str="http://localhost:3000"; rate_limit_requests:int=120; rate_limit_window_seconds:int=60
    whatsapp_provider:str="openwa"; openwa_base_url:str="http://localhost:2785"; openwa_api_key:str=""; openwa_session_id:str=""; openwa_webhook_secret:str=""; whatsapp_access_token:str=""; whatsapp_phone_number_id:str=""; razorpay_key_id:str=""; razorpay_key_secret:str=""
    turn_url:str=""; turn_username:str=""; turn_credential:str=""
    stt_provider:str="google"; tts_provider:str="google"; stt_api_key:str=""; tts_api_key:str=""
    telephony_provider:str=""; telephony_api_key:str=""; telephony_webhook_secret:str=""
    ai_voice_enabled:bool=False
    model_config=SettingsConfigDict(env_file=".env",extra="ignore")

settings=Settings()
