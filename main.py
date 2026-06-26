# =============================================================================
# API REST Dummy - Sistema de Backoffice para Optimizacion de Rutas
# =============================================================================
#
# DESCRIPCION:
#   Simula los endpoints externos de un sistema de backoffice que alimenta
#   un servicio de optimizacion de rutas. Todos los datos son ficticios y
#   se generan en memoria al iniciar el servidor.
#   Las Ordenes de Trabajo (OTs) se cargan desde el archivo
#   ordenes_de_trabajo.json en lugar de generarse aleatoriamente.
#
# INSTALACION DE DEPENDENCIAS:
#   pip install fastapi uvicorn faker
#
# EJECUCION DEL SERVIDOR:
#   uvicorn main:app --reload --port 8000
#
#   La documentacion interactiva estara disponible en:
#     - Swagger UI: http://127.0.0.1:8000/docs
#     - ReDoc:      http://127.0.0.1:8000/redoc
# =============================================================================

import json
import random
import uuid
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from faker import Faker
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# =============================================================================
# CONFIGURACION INICIAL
# =============================================================================

# Inicializamos Faker con locale espanol de Chile para datos mas realistas
fake = Faker("es_CL")
random.seed(42)   # Semilla fija para reproducibilidad de los datos mock
Faker.seed(42)

app = FastAPI(
    title="Backoffice API - Optimizacion de Rutas",
    description=(
        "API REST dummy que simula el sistema de backoffice para "
        "alimentar un servicio de optimizacion de rutas en Santiago, Chile."
    ),
    version="1.0.0",
)

# Permitimos cualquier origen para facilitar pruebas desde frontends locales
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# ENUMS Y CONSTANTES
# =============================================================================

TIPOS_TECNICO = ["interno", "externo"]

TIPOS_OT = [
    "instalacion_simple",
    "instalacion_con_corte",
    "mantencion",
    "retiro",
]

ESTADOS_OT = [
    "por_revisar",
    "por_asignar",
    "asignacion_por_confirmar",
    "asignada",
    "en_terreno",
    "finalizada",
    "enviada_cobranza",
]

# =============================================================================
# CARGA DE DIRECCIONES REALES DESDE JSON
# Archivo: direcciones_reales_chile.json
# Estructura: { "Region": [ { "lugar", "direccion", "comuna" } ] }
# =============================================================================

_JSON_PATH = Path(__file__).parent / "direcciones_reales_chile.json"

with _JSON_PATH.open(encoding="utf-8") as _f:
    _raw = json.load(_f)

# Aplanamos todas las entradas en una sola lista de dicts
DIRECCIONES_CHILE: list[dict] = [
    entrada
    for region in _raw.values()
    for entrada in region
]

# Lista unica de comunas para asignar a tecnicos
COMUNAS_CHILE: list[str] = sorted(
    {entrada["comuna"] for entrada in DIRECCIONES_CHILE}
)


# =============================================================================
# CARGA DE ORDENES DE TRABAJO DESDE JSON
# Archivo: ordenes_de_trabajo.json
# =============================================================================

_ORDENES_PATH = Path(__file__).parent / "ordenes_de_trabajo.json"

with _ORDENES_PATH.open(encoding="utf-8") as _f:
    DB_ORDENES: list[dict] = json.load(_f)


# =============================================================================
# GENERACION DE LA BASE DE DATOS EN MEMORIA
# =============================================================================

def generar_tecnicos(n: int = 20) -> list:
    """
    Genera una lista de tecnicos con datos ficticios.

    Args:
        n: Numero de tecnicos a generar.

    Returns:
        Lista de diccionarios representando tecnicos.
    """
    # Filtramos las comunas permitidas para tecnicos internos
    regiones_internos = [
        "Coquimbo",
        "Valparaíso",
        "Libertador General Bernardo O'Higgins",
    ]
    comunas_internos = list({
        entrada["comuna"]
        for region in regiones_internos
        if region in _raw
        for entrada in _raw[region]
    })

    tecnicos = []
    for _ in range(n):
        tipo_tecnico = random.choice(TIPOS_TECNICO)

        if tipo_tecnico == "interno":
            zona_seleccionada = random.choice(comunas_internos)
        else:
            zona_seleccionada = random.choice(COMUNAS_CHILE)

        tecnico = {
            "id": str(uuid.uuid4()),
            "nombre": fake.first_name(),
            "apellidos": f"{fake.last_name()} {fake.last_name()}",
            "tipo": tipo_tecnico,
            "zona": zona_seleccionada,
        }
        tecnicos.append(tecnico)
    return tecnicos


def generar_disponibilidades(tecnicos: list, dias: int = 14, max_sin_disponibilidad: int = 3) -> list:
    """
    Genera disponibilidades para cada tecnico en un rango de dias.

    Args:
        tecnicos: Lista de tecnicos existentes.
        dias: Cuantos dias hacia adelante generar disponibilidad.
        max_sin_disponibilidad: Maximo de tecnicos que pueden no tener ningun dia disponible.

    Returns:
        Lista de diccionarios representando disponibilidades.
    """
    disponibilidades = []
    hoy = date.today()

    # Determinamos cuales tecnicos podran quedar sin disponibilidad
    n_sin_disp = random.randint(0, max_sin_disponibilidad)
    ids_sin_disponibilidad = set(
        t["id"] for t in random.sample(tecnicos, n_sin_disp)
    )

    for tecnico in tecnicos:
        tecnico_sin_disp = tecnico["id"] in ids_sin_disponibilidad
        for offset in range(dias):
            fecha = hoy + timedelta(days=offset)
            # Los fines de semana tienen menor probabilidad de disponibilidad
            es_fin_de_semana = fecha.weekday() >= 5  # 5=Sabado, 6=Domingo
            prob_disponible = 0.3 if es_fin_de_semana else 0.8

            if tecnico_sin_disp:
                disponible = False
            else:
                disponible = random.random() < prob_disponible
                # Garantizamos que al menos el primer dia laboral sea disponible
                if not disponible and offset == 0 and not es_fin_de_semana:
                    disponible = True

            disponibilidad = {
                "id": str(uuid.uuid4()),
                "tecnico_id": tecnico["id"],
                "fecha": fecha.isoformat(),
                "disponible": disponible,
            }
            disponibilidades.append(disponibilidad)

    return disponibilidades


# =============================================================================
# INICIALIZACION DE LA BASE DE DATOS EN MEMORIA
# =============================================================================

# 1. Generamos los tecnicos aleatorios
DB_TECNICOS = generar_tecnicos(n=20)

# 2. Extraemos los tecnico_id referenciados en las OTs del JSON que NO existen
#    en DB_TECNICOS, y creamos registros de tecnico para ellos. Esto garantiza
#    que la validacion del endpoint PATCH /ordenes/{id}/tecnico siempre sea
#    consistente con los datos del JSON.
ids_tecnicos_existentes = {t["id"] for t in DB_TECNICOS}
ids_tecnicos_en_ots = {
    ot["tecnico_id"]
    for ot in DB_ORDENES
    if ot.get("tecnico_id") is not None
}

for tecnico_id_faltante in ids_tecnicos_en_ots - ids_tecnicos_existentes:
    DB_TECNICOS.append({
        "id": tecnico_id_faltante,
        "nombre": fake.first_name(),
        "apellidos": f"{fake.last_name()} {fake.last_name()}",
        "tipo": random.choice(TIPOS_TECNICO),
        "zona": random.choice(COMUNAS_CHILE),
    })

# 3. Generamos disponibilidades para todos los tecnicos (incluidos los del JSON)
DB_DISPONIBILIDADES = generar_disponibilidades(DB_TECNICOS, dias=14)


# =============================================================================
# MODELOS PYDANTIC (para validacion de request/response bodies)
# =============================================================================

class AsignarTecnicoRequest(BaseModel):
    """Body esperado para el endpoint PATCH /ordenes/{id}/tecnico."""
    tecnico_id: str


# =============================================================================
# ENDPOINTS
# =============================================================================

# --- Raiz ---

@app.get("/", tags=["Root"])
def root():
    """Endpoint raiz con informacion basica de la API."""
    return {
        "mensaje": "API Dummy - Sistema de Backoffice para Optimizacion de Rutas",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints_disponibles": [
            "GET  /api/tecnicos",
            "GET  /api/ordenes",
            "PATCH /api/ordenes/{id}/tecnico",
            "GET  /api/disponibilidad",
        ],
    }


# --- Tecnicos ---

@app.get(
    "/api/tecnicos",
    tags=["Tecnicos"],
    summary="Obtener lista de tecnicos",
    response_description="Lista completa de tecnicos registrados en el sistema.",
)
def get_tecnicos():
    """
    Retorna la lista completa de tecnicos disponibles en el sistema.

    Cada tecnico incluye:
    - **id**: Identificador unico (UUID)
    - **nombre**: Nombre del tecnico
    - **apellidos**: Apellidos del tecnico
    - **tipo**: interno o externo
    - **zona**: Zona asignada al tecnico
    """
    return DB_TECNICOS


# --- Ordenes de Trabajo ---

@app.get(
    "/api/ordenes",
    tags=["Ordenes de Trabajo"],
    summary="Obtener lista de ordenes de trabajo",
    response_description="Lista de ordenes de trabajo (OTs), opcionalmente filtrada por estado.",
)
def get_ordenes(
    estado: Optional[str] = Query(
        default=None,
        description=(
            "Filtra las OTs por estado. Valores validos: "
            "por_revisar | por_asignar | asignacion_por_confirmar | "
            "asignada | en_terreno | finalizada | enviada_cobranza"
        ),
        example="por_asignar",
    )
):
    """
    Retorna la lista de ordenes de trabajo (OTs) del sistema.
    Las OTs se cargan desde el archivo ordenes_de_trabajo.json.

    Acepta un query parameter opcional **estado** para filtrar los resultados:
    - Sin `estado`: retorna todas las OTs.
    - Con `estado` (ej: `?estado=por_asignar`): retorna solo las OTs con ese estado.

    Estados validos: por_revisar | por_asignar | asignacion_por_confirmar |
    asignada | en_terreno | finalizada | enviada_cobranza

    Cada OT incluye:
    - **id**: Identificador en formato OT-XXXX
    - **tipo**: Tipo de servicio (instalacion_simple, instalacion_con_corte, mantencion, retiro)
    - **estado**: Estado actual del flujo de trabajo
    - **tecnico_id**: UUID del tecnico asignado (puede ser null)
    - **direccion_instalacion**: Direccion del trabajo
    - **fecha_programada**: Fecha en formato ISO 8601 (puede ser null)
    - **hora_programada**: Hora en formato HH:MM (puede ser null)
    """
    if estado is None:
        return DB_ORDENES

    # Validamos que el estado sea uno de los valores permitidos
    if estado not in ESTADOS_OT:
        raise HTTPException(
            status_code=422,
            detail=(
                f"El estado '{estado}' no es valido. "
                f"Valores permitidos: {', '.join(ESTADOS_OT)}"
            ),
        )

    return [o for o in DB_ORDENES if o["estado"] == estado]


@app.patch(
    "/api/ordenes/{id}/tecnico",
    tags=["Ordenes de Trabajo"],
    summary="Asignar tecnico a una orden de trabajo",
    response_description="La orden de trabajo actualizada con el nuevo tecnico asignado.",
)
def asignar_tecnico(id: str, body: AsignarTecnicoRequest):
    """
    Simula la asignacion de un tecnico a una orden de trabajo especifica.

    - Busca la OT por su id (ej: OT-0001).
    - Valida que el tecnico_id del body corresponda a un tecnico existente.
    - Actualiza la OT en memoria con el nuevo tecnico_id.
    - Cambia el estado de la OT a asignacion_por_confirmar si estaba pendiente.
    - Retorna la OT actualizada.

    Body esperado: {"tecnico_id": "uuid-del-tecnico"}
    """
    # Buscamos la OT por id
    orden = next((o for o in DB_ORDENES if o["id"] == id), None)
    if orden is None:
        raise HTTPException(
            status_code=404,
            detail=f"Orden de trabajo con id '{id}' no encontrada.",
        )

    # Validamos que el tecnico exista en nuestra base de datos en memoria
    tecnico = next((t for t in DB_TECNICOS if t["id"] == body.tecnico_id), None)
    if tecnico is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tecnico con id '{body.tecnico_id}' no encontrado.",
        )

    # Actualizamos la OT en memoria
    orden["tecnico_id"] = body.tecnico_id

    # Si la OT estaba sin asignar, la movemos al siguiente estado logico
    if orden["estado"] in ("por_revisar", "por_asignar"):
        orden["estado"] = "asignacion_por_confirmar"

    return orden


# --- Disponibilidad ---

@app.get(
    "/api/disponibilidad",
    tags=["Disponibilidad"],
    summary="Obtener disponibilidades de tecnicos",
    response_description="Lista de disponibilidades, opcionalmente filtrada por fecha.",
)
def get_disponibilidad(
    fecha: Optional[str] = Query(
        default=None,
        description="Filtra las disponibilidades por fecha. Formato: YYYY-MM-DD",
        example="2026-06-20",
    )
):
    """
    Retorna la lista de disponibilidades de todos los tecnicos.

    Acepta un query parameter opcional fecha para filtrar los resultados:
    - Sin fecha: retorna todas las disponibilidades del rango generado (14 dias).
    - Con fecha (ej: ?fecha=2026-06-20): retorna solo las disponibilidades de ese dia.

    Cada entrada incluye:
    - **id**: Identificador unico (UUID)
    - **tecnico_id**: UUID del tecnico al que pertenece la disponibilidad
    - **fecha**: Fecha en formato ISO 8601
    - **disponible**: true si el tecnico esta disponible ese dia, false si no
    """
    if fecha is None:
        return DB_DISPONIBILIDADES

    # Validamos que el parametro tenga el formato correcto
    try:
        date.fromisoformat(fecha)
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=(
                f"El parametro 'fecha' tiene un formato invalido: '{fecha}'. "
                "Use el formato YYYY-MM-DD (ej: 2026-06-20)."
            ),
        )

    return [d for d in DB_DISPONIBILIDADES if d["fecha"] == fecha]
