import os
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.exc import OperationalError

# URL de conexión a PostgreSQL
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://kubermates:kubermates@db:5432/kubermates",
)

# Reintenta conectar si Postgres tarda en arrancar en Docker
def _create_engine_with_retry(url: str, attempts: int = 10, delay: float = 2.0):
    last_error = None
    for _ in range(attempts):
        try:
            engine = create_engine(url, pool_pre_ping=True)
            with engine.connect():
                pass
            return engine
        except OperationalError as exc:
            last_error = exc
            time.sleep(delay)
    raise RuntimeError(f"No se pudo conectar a la base de datos: {last_error}")


# Motor global y sesión
engine = _create_engine_with_retry(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# Generador de sesión para inyección de dependencias en FastAPI
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()