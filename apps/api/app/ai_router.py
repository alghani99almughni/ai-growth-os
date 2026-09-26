import re
from difflib import SequenceMatcher
from sqlalchemy import select
from sqlalchemy.orm import Session
from .models_ai import GlobalFaq
from .models import Service, Product
LANGUAGE_PATTERNS={"en":r"[a-z]","hi":r"[\u0900-\u097f]","te":r"[\u0c00-\u0c7f]","ta":r"[\u0b80-\u0bff]","kn":r"[\u0c80-\u0cff]","ml":r"[\u0d00-\u0d7f]","mr":r"[\u0900-\u097f]","bn":r"[\u0980-\u09ff]","gu":r"[\u0a80-\u0aff]","pa":r"[\u0a00-\u0a7f]","or":r"[\u0b00-\u0b7f]","as":r"[\u0980-\u09ff]","ur":r"[\u0600-\u06ff]"}
def detect_language(text:str)->str:
    scores={k:len(re.findall(p,text)) for k,p in LANGUAGE_PATTERNS.items()}
    if max(scores.values(),default=0)>0:
        winner=max(scores,key=scores.get)
        if winner=="hi" and re.search(r"\b(आहे|मला|काय|कुठे)\b",text): return "mr"
        if winner=="bn" and re.search(r"[অআইঈউএও]",text): return "bn"
        return winner
    explicit_languages={
        "hi":("hindi","हिंदी","हिन्दी"), "te":("telugu","telugulo","తెలుగు"),
        "ta":("tamil","tamil la","தமிழ்"), "kn":("kannada","kannadadalli","ಕನ್ನಡ"),
        "ml":("malayalam","malayalathil","മലയാളം"), "mr":("marathi","marathit","मराठी"),
        "bn":("bengali","banglay","বাংলা"), "gu":("gujarati","gujarati ma","ગુજરાતી"),
        "pa":("punjabi","punjabi vich","ਪੰਜਾਬੀ"), "ur":("urdu","urdu mein","اردو"),
    }
    for lang,markers in explicit_languages.items():
        if any(marker in text.casefold() for marker in markers):
            return lang
    romanized=text.casefold()
    roman_scores={
        "hi":("mujhe","aap","aapke","kya","hai","hain","chahiye","karna","bataiye","hindi"),
        "te":("naaku","meeru","repu","enti","kavali","cheyyali","matladagalara","telugu"),
        "ta":("enakku","ungal","naalai","venum","pannanum","eppo","pesanum","tamil"),
        "kn":("nanage","nimma","naale","beku","madbeku","maatadbeku","kannada"),
        "ml":("enikku","ningalude","naale","venam","enthaa","eppozha","malayalam"),
        "mr":("mala","tumche","udya","aahe","kay","havi","marathi"),
        "bn":("amar","apnader","korte","chai","koto","kokhon","bengali"),
        "gu":("mane","tamara","kaale","joiye","shu","chhe","gujarati"),
        "pa":("mainu","tuhade","chahidi","kadon","kinna","gal","punjabi"),
        "ur":("mujhe","aapke","kaun","bataiye","urdu"),
    }
    ranked={lang:sum(1 for marker in markers if marker in romanized) for lang,markers in roman_scores.items()}
    winner,score=max(ranked.items(),key=lambda item:item[1])
    return winner if score>=2 else "en"
def normalize(text:str)->set[str]:
    return {x.casefold() for x in re.findall(r"[\w\u00c0-\uffff]{2,}",text,flags=re.UNICODE)}
def _score(message:str,candidate:str)->float:
    incoming,source=normalize(message),normalize(candidate)
    if not incoming or not source:return 0.0
    return max(len(incoming&source)/max(1,len(incoming)),SequenceMatcher(None,message.casefold(),candidate.casefold()).ratio()*0.65)
def faq_match(db:Session,industry:str,message:str,language:str)->GlobalFaq|None:
    rows=db.scalars(select(GlobalFaq).where(GlobalFaq.is_active==True,GlobalFaq.language.in_([language,"en"]),GlobalFaq.industry.in_([industry,"general"]))).all()
    best,best_score=None,0.0
    for row in rows:
        score=_score(message,(row.question or "")+" "+(row.keywords or ""))
        if score>best_score:best_score,best=score,row
    return best if best_score>=0.55 else None
def structured_match(db:Session,tenant_id:str,message:str)->str|None:
    m=message.casefold()
    if any(x in m for x in ("price","cost","fee","rate","how much","कीमत","ధర","விலை")):
        services=db.scalars(select(Service).where(Service.tenant_id==tenant_id,Service.is_active==True)).all()
        if services:return "Here are the currently configured services and prices: "+"; ".join(f"{s.name}: {s.price} {s.currency}" for s in services if s.price is not None)
    if any(x in m for x in ("product","buy","order","stock","available","उत्पाद","ధర")):
        products=db.scalars(select(Product).where(Product.tenant_id==tenant_id,Product.is_active==True)).all()
        if products:return "Here are the currently configured products: "+"; ".join(f"{p.name}: {p.price} {p.currency}" for p in products if p.price is not None)
    return None
def knowledge_match(db:Session,tenant_id:str,message:str)->str|None:
    from .models_growth import KnowledgeItem
    rows=db.scalars(select(KnowledgeItem).where(KnowledgeItem.tenant_id==tenant_id,KnowledgeItem.is_active==True,KnowledgeItem.approval_status.in_(["approved","system"]))).all()
    language,incoming=detect_language(message),normalize(message)
    # Expand common domain wording so short questions such as “may I know the
    # doctor” can match a tenant knowledge item titled “Doctor / Provider”.
    if any(x in message.casefold() for x in ("doctor","dr ","provider","physician","डॉक्टर","డాక్టర్","மருத்துவர்")):
        incoming |= {"doctor","provider","physician"}
    if not incoming:return None
    best,best_score=None,0.0
    for row in rows:
        if row.language and row.language not in {language,"en"}:continue
        score=_score(message,(row.title or "")+" "+(row.content or ""))
        if row.language==language:score+=0.08
        if score>best_score:best_score,best=score,row
    return best.content if best and best_score>=0.38 else None    