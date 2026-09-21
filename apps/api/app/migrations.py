from .db import Base,engine
from . import models,models_growth
def ensure_schema(): Base.metadata.create_all(bind=engine)
