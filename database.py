import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker, DeclarativeBase



load_dotenv()

DB_PASSWORD = os.getenv("DB_PASSWORD")

if not DB_PASSWORD:
    raise RuntimeError("DB_PASSWORD не найден в .env")




# Подключение к PostgreSQL
DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username="postgres",
    password=DB_PASSWORD,
    host="localhost",
    port=5432,
    database="todo_db"
)

# Создаём подключение
engine = create_engine(
    DATABASE_URL,
    echo=True
)

# Создаём фабрику сессий
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)


# Базовый класс моделей
class Base(DeclarativeBase):
    pass