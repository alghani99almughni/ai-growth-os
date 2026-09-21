from .db import Base,engine
from . import models,models_growth,models_ai

def ensure_schema():
    Base.metadata.create_all(bind=engine)
