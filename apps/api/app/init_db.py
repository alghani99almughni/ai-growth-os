from .db import Base,engine
from . import models,models_growth
def init_db(): Base.metadata.create_all(bind=engine)
if __name__=="__main__": init_db()
