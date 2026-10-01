"""Provider-neutral realtime voice turn controller."""

from dataclasses import dataclass, field
from enum import Enum
import time

class VoiceTurn(str, Enum):
    IDLE="idle"
    LISTENING="listening"
    THINKING="thinking"
    SPEAKING="speaking"
    INTERRUPTED="interrupted"

@dataclass
class VoiceTurnTrace:
    turn_index:int
    started_at:float
    input_final_at:float|None=None
    first_output_at:float|None=None
    completed_at:float|None=None

    @property
    def voice_to_first_audio_ms(self):
        if self.input_final_at is None or self.first_output_at is None:
            return None
        return max(0,round((self.first_output_at-self.input_final_at)*1000))

@dataclass
class VoiceTurnController:
    state:VoiceTurn=VoiceTurn.IDLE
    turn_index:int=0
    interruption_count:int=0
    last_interruption_at:float=0.0
    traces:list[VoiceTurnTrace]=field(default_factory=list)
    active:VoiceTurnTrace|None=None

    def begin(self,now=None):
        now=now or time.monotonic()
        self.turn_index+=1
        self.active=VoiceTurnTrace(self.turn_index,now)
        self.state=VoiceTurn.LISTENING

    def input_final(self,now=None):
        now=now or time.monotonic()
        if self.active is None:self.begin(now)
        self.active.input_final_at=now
        self.state=VoiceTurn.THINKING

    def output(self,now=None):
        now=now or time.monotonic()
        if self.active is None:self.begin(now)
        self.active.first_output_at=self.active.first_output_at or now
        self.state=VoiceTurn.SPEAKING

    def interrupt(self,now=None):
        now=now or time.monotonic()
        if now-self.last_interruption_at<0.2:return False
        self.last_interruption_at=now
        self.interruption_count+=1
        self.state=VoiceTurn.INTERRUPTED
        return True

    def complete(self,now=None):
        if self.active is None:return None
        self.active.completed_at=now or time.monotonic()
        trace=self.active
        self.traces.append(trace)
        self.active=None
        self.state=VoiceTurn.IDLE
        return trace
