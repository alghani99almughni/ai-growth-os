from dataclasses import dataclass
@dataclass
class VoiceProvider:
    name:str="adapter"
    async def transcribe(self,audio:bytes)->str: raise NotImplementedError("Configure an STT provider")
    async def synthesize(self,text:str)->bytes: raise NotImplementedError("Configure a TTS provider")
@dataclass
class CallState:
    CREATED:str="created"; RINGING:str="ringing"; ACCEPTED:str="accepted"; CONNECTING:str="connecting"; CONNECTED:str="connected"; ENDED:str="ended"; REJECTED:str="rejected"; MISSED:str="missed"; FAILED:str="failed"; TIMEOUT:str="timeout"; CANCELLED:str="cancelled"; TRANSFERRED:str="transferred"
