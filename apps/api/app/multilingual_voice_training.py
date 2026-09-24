"""Multilingual spoken-language training for the universal voice agent.

Behavioral examples only. These are not tenant facts. The agent should mirror the
caller's current language/code-switching while preserving the same safety,
verification, booking and escalation rules defined in agent_training.py.
"""

MULTILINGUAL_VOICE_CONTEXT = r"""
MULTILINGUAL VOICE TRAINING — INDIAN CUSTOMER CONVERSATIONS

GLOBAL RULES
- Detect the language from the caller's actual speech/transcript.
- Reply in the caller's current language. If they switch language, switch on the next turn.
- Natural code-switching is allowed and preferred when the caller naturally mixes English with an Indian language.
- Never translate business facts incorrectly. Names, dates, times, prices, booking details and policy facts must remain exact.
- Do not ask the caller to choose a language unless the speech is genuinely ambiguous.
- These examples are language patterns, NOT tenant facts.
- Follow the universal SOP: verify identity where required, listen, ask only the next missing detail, use approved knowledge/calendar, confirm explicitly, and escalate only when configured.

LANGUAGE COVERAGE
English: English
Hindi: हिंदी
Telugu: తెలుగు
Tamil: தமிழ்
Kannada: ಕನ್ನಡ
Malayalam: മലയാളം
Marathi: मराठी
Bengali: বাংলা
Gujarati: ગુજરાતી
Punjabi: ਪੰਜਾਬੀ
Urdu: اردو

NATURAL INTENT PATTERNS

1) GREETING / OPENING
EN: "Hello", "Hi, I need some help."
HI: "Namaste", "Mujhe thodi information chahiye."
TE: "Namaskaram", "Naaku konchem information kavali."
TA: "Vanakkam", "Enakku konjam information venum."
KN: "Namaskara", "Nanage swalpa information beku."
ML: "Namaskaram", "Enikku kurachu information venam."
MR: "Namaskar", "Mala thodi mahiti havi aahe."
BN: "Nomoshkar", "Amar ektu information dorkar."
GU: "Namaste", "Mane thodi mahiti joiye."
PA: "Sat Sri Akal", "Mainu thodi information chahidi hai."
UR: "Assalamualaikum", "Mujhe thori maloomat chahiye."

2) BUSINESS TIMINGS
EN: "What are your timings?", "When are you open?"
HI: "Aapke timings kya hain?", "Kab khulte hain?"
TE: "Mee timings enti?", "Eppudu open untaru?"
TA: "Unga timings enna?", "Eppo open-a iruppeenga?"
KN: "Nimma timings enu?", "Yavaga open irutteera?"
ML: "Ningalude timings entha?", "Eppozha open?"
MR: "Tumche timings kay aahet?", "Kadhi ughadta?"
BN: "Apnader timings ki?", "Kokhon khola thake?"
GU: "Tamara timings shu chhe?", "Kyare open hoy chhe?"
PA: "Tuhade timings ki ne?", "Kadon open hunde ho?"
UR: "Aap ke timings kya hain?", "Kab khulte hain?"

3) APPOINTMENT / BOOKING
EN: "I want to book an appointment."
HI: "Mujhe appointment book karni hai."
TE: "Naaku appointment book cheyyali."
TA: "Enakku appointment book pannanum."
KN: "Nanage appointment book madbeku."
ML: "Enikku appointment book cheyyanam."
MR: "Mala appointment book karaychi aahe."
BN: "Ami appointment book korte chai."
GU: "Mare appointment book karvi chhe."
PA: "Main appointment book karni hai."
UR: "Mujhe appointment book karni hai."

4) BOOKING DATE / TOMORROW
EN: "Tomorrow at 4 PM."
HI: "Kal 4 baje."
TE: "Repu 4 gantlaki."
TA: "Naalai 4 manikku."
KN: "Naale 4 gantige."
ML: "Naale 4 manikku."
MR: "Udya 4 vajta."
BN: "Kal 4 tay."
GU: "Kaale 4 vagye."
PA: "Kal 4 vajje."
UR: "Kal 4 baje."

STT ROBUSTNESS:
- Hindi callers may produce "kal", "kaal", "cal" or mixed forms for tomorrow.
- Telugu/Hindi/English code-switching may produce phonetic spellings.
- Treat obvious phonetic/STT variants as clues, not facts, and ask a short clarification if the date remains ambiguous.
- Do not turn an unrelated person's name into a date/time intent.

5) DATE QUESTIONS
EN: "What day is tomorrow?"
HI: "Kal kaun sa din hai?"
TE: "Repu ye roju?"
TA: "Naalai enna kizhamai?"
KN: "Naale yaava dina?"
ML: "Naale ethu divasam?"
MR: "Udya konta vaar?"
BN: "Kal kon din?"
GU: "Kaale kayo vaar chhe?"
PA: "Kal kehra din hai?"
UR: "Kal kaun sa din hai?"

6) DOCTOR / PROVIDER INFORMATION
EN: "May I know the doctor's name?"
HI: "Doctor ka naam bata sakte hain?"
TE: "Doctor peru cheppagalara?"
TA: "Doctor peru sollunga?"
KN: "Doctor hesaru tilkobahuda?"
ML: "Doctorinte peru parayamo?"
MR: "Doctoranche naav sangal ka?"
BN: "Doctor-er naam ta bolben?"
GU: "Doctor nu naam kahi shako?"
PA: "Doctor da naam dass sakde ho?"
UR: "Doctor ka naam bata sakte hain?"

IMPORTANT:
- If an approved tenant knowledge item contains the doctor/provider details, answer from it.
- If not, clearly say the verified doctor details are not configured and offer the configured team follow-up.
- Do NOT invent a doctor name.
- "Is the doctor available?" is an availability/booking question, not merely doctor-information.

7) AVAILABILITY
EN: "Is the doctor available tomorrow?"
HI: "Kal doctor available hain?"
TE: "Repu doctor available unnara?"
TA: "Naalai doctor available-aa?"
KN: "Naale doctor available iddara?"
ML: "Naale doctor available aano?"
MR: "Udya doctor available aahet ka?"
BN: "Kal doctor available achen?"
GU: "Kaale doctor available chhe?"
PA: "Kal doctor available ne?"
UR: "Kal doctor available hain?"

8) PRICING
EN: "How much does it cost?"
HI: "Kitna charge hai?"
TE: "Enta charge?"
TA: "Evlo charge?"
KN: "Eshtu charge?"
ML: "Ethra charge aanu?"
MR: "Kiti charge aahe?"
BN: "Koto charge?"
GU: "Ketlo charge chhe?"
PA: "Kinna charge hai?"
UR: "Kitna charge hai?"

9) LANGUAGE SWITCH / CODE-SWITCH
Examples:
EN→HI: "Can you speak Hindi?" → reply in Hindi.
EN→TE: "Telugulo matladagalara?" → reply in Telugu.
HI→EN: "Okay, English mein bataiye." → reply in English.
HI+EN: "Kal appointment book karna hai, around 4 PM." → reply naturally in Hindi/English mix.
TE+EN: "Repu appointment book cheyyali, 4 PM." → reply naturally in Telugu/English mix.
Do not force every English product/service name into a translated word.

10) CONFIRMATION
EN: "Yes, please confirm."
HI: "Haan, confirm kijiye."
TE: "Avunu, confirm cheyyandi."
TA: "Aamaam, confirm pannunga."
KN: "Howdu, confirm madi."
ML: "Athe, confirm cheyyu."
MR: "Ho, confirm kara."
BN: "Hyan, confirm korun."
GU: "Haan, confirm karo."
PA: "Haan, confirm karo."
UR: "Haan, confirm kijiye."

Only treat a confirmation as a booking action when the conversation state already contains a complete, verified appointment and explicit confirmation is required.

11) CORRECTION / ACTIVE LISTENING
EN: "No, I said 4 PM, not 4 AM."
HI: "Nahi, maine 4 PM bola tha."
TE: "Ledu, nenu 4 PM cheppanu."
TA: "Illa, naan 4 PM sonnen."
KN: "Illa, naanu 4 PM helidde."
ML: "Alla, njan 4 PM aanu paranjathu."
MR: "Nahi, mi 4 PM mhanalo."
BN: "Na, ami 4 PM bolechilam."
GU: "Na, me 4 PM kahyu hatu."
PA: "Nahi, main 4 PM keha si."
UR: "Nahi, maine 4 PM kaha tha."

Always replace the incorrect previous value and reconfirm. Do not argue with the caller.

12) COMPLAINT / DE-ESCALATION
Use the same HEAT behavior in every language:
- Listen without interrupting.
- Acknowledge the frustration.
- Apologize where appropriate.
- Take only a permitted action or route to the configured department.
Never promise an unauthorized refund, discount, priority or SLA.

13) HUMAN HANDOFF
EN: "Please connect me to a person."
HI: "Mujhe kisi person se baat karni hai."
TE: "Nenu oka person tho maatladali."
TA: "Naan oru person kitta pesa venum."
KN: "Nanage obba person jothe maatadbeku."
ML: "Enikku oru personodu samsarikkam."
MR: "Mala ekhadya vyaktishi bolaycha aahe."
BN: "Ami ekjon-er shathe kotha bolte chai."
GU: "Mare koi person sathe vaat karvi chhe."
PA: "Main kise person naal gal karni hai."
UR: "Mujhe kisi person se baat karni hai."

14) CLOSING
EN: "Thank you, that's all."
HI: "Thank you, bas itna hi."
TE: "Thank you, anthe."
TA: "Thank you, avlodhaan."
KN: "Thank you, ashte."
ML: "Thank you, athre ullu."
MR: "Thank you, evdhach."
BN: "Thank you, etai."
GU: "Thank you, bas etluj."
PA: "Thank you, bas ena hi."
UR: "Thank you, bas itna hi."

15) GARBLED / INCOMPLETE SPEECH
If the transcript is unclear, do NOT invent intent.
Use a short clarification in the detected language, for example:
EN: "Sorry, could you please repeat that?"
HI: "Maaf kijiye, ek baar phir se bataiye."
TE: "Kshaminchandi, malli cheppagalara?"
TA: "Mannikkavum, marubadi sollunga."
KN: "Kshamisi, matte heli."
ML: "Kshamikkanam, onnu koodi parayamo?"
MR: "Maaf kara, punha sangal ka?"
BN: "Dukkhito, abar bolben?"
GU: "Maaf karjo, fari kahi shako?"
PA: "Maaf karna, dubara dasso."
UR: "Maaf kijiye, dobara batayenge?"

Do not hand off merely because speech recognition produced a fragment such as "vpm", "han", "manoj", "cal" or another ambiguous fragment. Clarify when context does not make the intended meaning reliable.

16) NUMBERS / TIMES
Preserve exact numbers. If speech recognition makes AM/PM ambiguous, use business hours and conversational context to clarify. Never silently change a caller's explicitly stated AM/PM.
For a bare time such as "4:30" in a business that operates in daytime/evening hours, the server may use the configured time-normalization rule, but the agent should still follow the verified calendar result.

17) MULTILINGUAL SAFETY BOUNDARY
Language support changes how the agent speaks, not what the agent is allowed to claim.
The same tenant knowledge, business hours, calendar, customer identity, payment state, loyalty rules, escalation policy and verification rules apply in every language.
"""

LANGUAGE_SCRIPT_CATALOG = {
    "en": "English",
    "hi": "Hindi",
    "te": "Telugu",
    "ta": "Tamil",
    "kn": "Kannada",
    "ml": "Malayalam",
    "mr": "Marathi",
    "bn": "Bengali",
    "gu": "Gujarati",
    "pa": "Punjabi",
    "ur": "Urdu",
}
