import os 
from sqlalchemy import create_engine 
from sqlalchemy.orm import sessionmaker, DeclarativeBase 
  
BASE_DIR = os.path.dirname(os.path.abspath(__file__)) 
  
# sqlite:/// uses Python's built-in sqlite3 driver automatically 
DATABASE_URL = f"sqlite:///{os.path.join(BASE_DIR, 'app.db')}" 
  
engine = create_engine( 
    DATABASE_URL, 
    connect_args={"check_same_thread": False},  # required for SQLite 
    echo=True,   # prints SQL to terminal — set False in production 
) 
  
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False) 
  
class Base(DeclarativeBase): 
    pass
