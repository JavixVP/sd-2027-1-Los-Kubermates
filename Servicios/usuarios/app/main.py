"""Servicio Usuarios: dueño exclusivo de los datos de los usuarios (PRD sección 6)."""
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
import asyncpg

from . import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.conectar()
    yield
    await db.cerrar()


app = FastAPI(title="Usuarios", lifespan=lifespan)

# Habilita CORS para que el frontend (servido en otro origen/puerto) pueda llamar
# a la API a través del gateway. Es un proyecto de demostración/clase (PRD fuera de
# alcance: seguridad de producción), así que se permite cualquier origen.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class UsuarioCrear(BaseModel):
    nombre: str = Field(min_length=1)
    correo: EmailStr


class Usuario(BaseModel):
    id: UUID
    nombre: str
    correo: str


@app.get("/salud")
async def salud():
    return {"estado": "ok"}


@app.post("/usuarios", response_model=Usuario, status_code=201)
async def crear_usuario(cuerpo: UsuarioCrear):
    async with db.pool().acquire() as con:
        try:
            fila = await con.fetchrow(
                "INSERT INTO usuarios (nombre, correo) VALUES ($1, $2) "
                "RETURNING id, nombre, correo",
                cuerpo.nombre,
                cuerpo.correo,
            )
        except asyncpg.UniqueViolationError as exc:
            raise HTTPException(status_code=409, detail="El correo ya está registrado") from exc
    return dict(fila)


@app.get("/usuarios/{usuario_id}", response_model=Usuario)
async def obtener_usuario(usuario_id: UUID):
    async with db.pool().acquire() as con:
        fila = await con.fetchrow(
            "SELECT id, nombre, correo FROM usuarios WHERE id = $1", usuario_id
        )
    if fila is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return dict(fila)


@app.get("/usuarios", response_model=list[Usuario])
async def listar_usuarios(correo: str | None = None):
    """Con ?correo= filtra por correo exacto. Lo usa el frontend para que un
    usuario "inicie sesión" con su correo sin necesitar un sistema de
    autenticación completo (fuera del alcance del PRD)."""
    async with db.pool().acquire() as con:
        if correo:
            filas = await con.fetch(
                "SELECT id, nombre, correo FROM usuarios WHERE correo = $1", correo
            )
        else:
            filas = await con.fetch("SELECT id, nombre, correo FROM usuarios ORDER BY creado_en")
    return [dict(f) for f in filas]
