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
import os
import random
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import psycopg2
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

# Regiones habilitadas para técnicos y órdenes de trabajo
REGIONES_OBJETIVO = [
    "Metropolitana de Santiago",
    "Valparaíso",
    "Libertador General Bernardo O'Higgins",
]

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

MOTIVOS_REPROGRAMACION = [
    "Cliente No Disponible",
    "Falta de Coordinación",
    "Técnico No Disponible",
    "Falta de Tiempo",
    "Problema de Ruta",
    "Problema Técnico",
    "Dirección Incorrecta",
    "Cliente Solicitó Cambio",
    "Otro",
]

TIPOS_MODIFICACION_PATCH = [
    "OT asignada a otro técnico",
    "OT reordenada",
    "OT descartada",
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
# GENERACION DE LA BASE DE DATOS EN MEMORIA
# =============================================================================

def generar_tecnicos() -> list:
    """
    Genera la lista fija de tecnicos agrupados por region y tipo:
      - 4 internos en Region de Valparaiso
      - 3 externos en Region de Valparaiso
      - 3 externos en Region Metropolitana de Santiago
      - 3 externos en Region del Libertador General Bernardo O'Higgins

    La zona de cada tecnico se asigna a una comuna perteneciente
    a su region de disponibilidad.

    Returns:
        Lista de diccionarios representando tecnicos.
    """
    # Definicion fija de grupos: (tipo, clave_region_en_json, cantidad)
    GRUPOS_TECNICOS = [
        ("interno", "Valparaíso",                                    4),
        ("externo", "Valparaíso",                                    3),
        ("externo", "Metropolitana de Santiago",                     3),
        ("externo", "Libertador General Bernardo O'Higgins",         3),
    ]

    tecnicos = []
    for tipo, region_key, cantidad in GRUPOS_TECNICOS:
        comunas_region = [e["comuna"] for e in _raw.get(region_key, [])]
        for _ in range(cantidad):
            tecnico = {
                "id": str(uuid.uuid4()),
                "nombre": fake.first_name(),
                "apellidos": f"{fake.last_name()} {fake.last_name()}",
                "tipo": tipo,
                "zona": random.choice(comunas_region),
                "region": region_key,
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


def generar_ordenes() -> list:
    """
    Genera las ordenes de trabajo en memoria usando las direcciones reales
    del archivo direcciones_reales_chile.json.

    Distribucion fija:
      - 8 OTs en Region de Valparaiso
      - 5 OTs en Region Metropolitana de Santiago
      - 5 OTs en Region del Libertador General Bernardo O'Higgins

    Todas las OTs se crean con estado 'por_asignar' y sin tecnico asignado.

    Returns:
        Lista de diccionarios representando ordenes de trabajo.
    """
    GRUPOS_ORDENES = [
        ("Valparaíso",                                  8),
        ("Metropolitana de Santiago",                   5),
        ("Libertador General Bernardo O'Higgins",       5),
    ]

    ordenes = []
    contador = 1

    for region_key, cantidad in GRUPOS_ORDENES:
        pool = _raw.get(region_key, [])
        # Seleccionamos 'cantidad' direcciones sin repeticion (el pool siempre es suficiente)
        seleccionadas = random.sample(pool, cantidad)

        for entrada in seleccionadas:
            hora_aleatoria = random.randint(12, 20)
            ot = {
                "id": f"OT-{contador:04d}",
                "tipo": random.choice(TIPOS_OT),
                "estado": "por_asignar",
                "tecnico_id": None,
                "direccion_instalacion": entrada["direccion"],
                "comuna": entrada["comuna"],
                "region": region_key,
                "fecha_programada": date.today().isoformat(),
                "hora_programada": f"{hora_aleatoria:02d}:00",
            }
            ordenes.append(ot)
            contador += 1

    return ordenes



# =============================================================================
# INICIALIZACION DE LA BASE DE DATOS EN MEMORIA
# =============================================================================

# 1. Generamos los tecnicos fijos por region
DB_TECNICOS = generar_tecnicos()

# 2. Generamos las OTs desde las direcciones reales del JSON
DB_ORDENES: list[dict] = generar_ordenes()

# 3. Generamos disponibilidades para los 13 tecnicos (14 dias)
DB_DISPONIBILIDADES = generar_disponibilidades(DB_TECNICOS, dias=14)



# =============================================================================
# MODELOS PYDANTIC (para validacion de request/response bodies)
# =============================================================================

class RevisadoPor(BaseModel):
    """Informacion del usuario que reviso la propuesta de asignacion."""
    usuario_id: str
    nombre: str
    rol: str


class AsignarTecnicoRequest(BaseModel):
    """
    Body esperado para el endpoint PATCH /ordenes/{id}/tecnico.

    tecnico_id puede ser null para el caso 'OT descartada'
    (se saca de un tecnico y queda sin asignar).
    """
    tecnico_id: Optional[str] = None
    motivo_reprogramacion: Optional[str] = None
    revisado_por: Optional[RevisadoPor] = None
    tipo_modificacion: Optional[str] = None


class ResumenCorrida(BaseModel):
    """Resumen estadistico de la corrida de optimizacion."""
    total_ots: int
    ots_asignadas: int
    ots_pendientes: int
    total_tecnicos: int
    tecnicos_utilizados: int
    distancia_total_km: float
    fuente_matriz: str


class ParadaRuta(BaseModel):
    """Detalle de una parada dentro de la ruta de un tecnico."""
    ot_id: str
    secuencia: int
    tipo: str
    direccion: str
    hora_estimada_llegada: str
    espera_min: int


class RutaTecnico(BaseModel):
    """Ruta asignada a un tecnico, incluyendo propuesta original y version final."""
    tecnico_id: str
    tecnico_nombre: str
    zona_base: str
    distancia_total_km: float
    capacidad_uso: str
    hora_salida_base: str
    hora_retorno_base: str
    ruta_propuesta: list[str]
    ruta_final: list[str]
    aceptada_sin_modificacion: bool
    modificaciones: list[dict] = []
    paradas: list[ParadaRuta]


class AsignarTecnicosRequest(BaseModel):
    """
    Body esperado para el endpoint POST /api/asignar-tecnicos.

    Representa el resultado de una corrida de optimizacion revisada
    y aprobada por un dispatcher/coordinador.
    """
    fecha_planificacion: str
    generado_en: str
    revisado_en: str
    revisado_por: RevisadoPor
    resumen_corrida: ResumenCorrida
    rutas: list[RutaTecnico]
    pendientes: list[dict] = []


# =============================================================================
# CONEXION A BASE DE DATOS POSTGRESQL (Render)
# =============================================================================

def get_db_connection():
    """
    Crea y retorna una conexion a la base de datos PostgreSQL
    usando la variable de entorno DATABASE_URL.

    Render entrega URLs con esquema 'postgres://' pero psycopg2
    requiere 'postgresql://'. Esta funcion hace el reemplazo
    automaticamente.

    Returns:
        psycopg2 connection object.

    Raises:
        ValueError: Si DATABASE_URL no esta configurada.
    """
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise ValueError(
            "La variable de entorno DATABASE_URL no esta configurada. "
            "Agreguela al archivo .env o como variable de entorno del sistema."
        )
    # Render usa 'postgres://' pero psycopg2 espera 'postgresql://'
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    return psycopg2.connect(database_url)


# =============================================================================
# MIGRACIONES DE BASE DE DATOS (se ejecutan al iniciar el servidor)
# =============================================================================

@app.on_event("startup")
def ensure_db_schema():
    """
    Asegura que las columnas de la tabla asignacion que dependen de datos
    del optimizador sean nullable.

    Esto es necesario porque los eventos de tipo 'OT descartada' no tienen
    un tecnico propuesto ni aceptado, y otros campos pueden no aplicar
    segun el tipo de evento. Solo se mantienen NOT NULL:
      - id (PK, auto-generado)
      - propuesta_modificada (boolean con default false, siempre se setea)

    Cada ALTER es idempotente (seguro de ejecutar multiples veces).
    """
    columnas_nullable = [
        "id_propuesta",
        "id_aceptada",
        "id_orden_trabajo",
        "fecha_asignacion",
        "fecha_orden_de_trabajo",
        "motivo_reprogramacion",
        "usuario_dispatcher",
        "fecha_generacion",
        "tipo_modificacion",
    ]
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for columna in columnas_nullable:
            cur.execute(
                f"ALTER TABLE asignacion "
                f"ALTER COLUMN {columna} DROP NOT NULL"
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception:
        # Las columnas ya son nullable, o la BD no esta disponible al iniciar
        pass


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
            "GET  /api/reset",
            "GET  /api/disponibilidad",
            "PATCH /api/ordenes/{id}/tecnico",
            "POST /api/asignar-tecnicos",
        ],
    }


# --- Reset ---

@app.get(
    "/api/reset",
    tags=["Admin"],
    summary="Reiniciar y regenerar todos los datos",
    response_description="Confirmacion del reset con conteo de registros generados.",
)
def reset():
    """
    Regenera en memoria todos los datos de la API:
    tecnicos, ordenes de trabajo y disponibilidades.

    Util para volver al estado inicial tras asignaciones u otras
    modificaciones realizadas durante la sesion.

    Retorna un resumen con la cantidad de registros generados.
    """
    global DB_TECNICOS, DB_ORDENES, DB_DISPONIBILIDADES

    DB_TECNICOS = generar_tecnicos()
    DB_ORDENES = generar_ordenes()
    DB_DISPONIBILIDADES = generar_disponibilidades(DB_TECNICOS, dias=14)

    return {
        "mensaje": "Reset completado. Todos los datos han sido regenerados.",
        "tecnicos": len(DB_TECNICOS),
        "ordenes": len(DB_ORDENES),
        "disponibilidades": len(DB_DISPONIBILIDADES),
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
    summary="Asignar o reprogramar tecnico de una orden de trabajo",
    response_description="La orden de trabajo actualizada con el estado de persistencia en BD.",
)
def asignar_tecnico(id: str, body: AsignarTecnicoRequest):
    """
    Asigna, reprograma o descarta la asignacion de un tecnico a una OT.
    Cada invocacion inserta una fila nueva en la tabla `asignacion` de
    PostgreSQL (historial de eventos, nunca se sobrescribe).

    Casos de uso:
    - **Asignar**: tecnico_id con UUID, sin motivo_reprogramacion.
    - **Reprogramar**: tecnico_id con UUID nuevo, con motivo_reprogramacion.
    - **Descartar**: tecnico_id null, con motivo_reprogramacion y
      tipo_modificacion = "OT descartada". La OT vuelve a estado por_asignar.

    Body esperado:
    {
        "tecnico_id": "uuid-o-null",
        "motivo_reprogramacion": "texto del motivo",
        "revisado_por": {"usuario_id": "u1", "nombre": "Camila Soto", "rol": "Coordinadora"},
        "tipo_modificacion": "OT asignada a otro técnico"
    }
    """
    # Buscamos la OT por id
    orden = next((o for o in DB_ORDENES if o["id"] == id), None)
    if orden is None:
        raise HTTPException(
            status_code=404,
            detail=f"Orden de trabajo con id '{id}' no encontrada.",
        )

    # Validamos que el tecnico exista (solo si se envia un tecnico_id)
    if body.tecnico_id is not None:
        tecnico = next(
            (t for t in DB_TECNICOS if t["id"] == body.tecnico_id), None
        )
        if tecnico is None:
            raise HTTPException(
                status_code=404,
                detail=f"Tecnico con id '{body.tecnico_id}' no encontrado.",
            )

    # Validamos motivo_reprogramacion contra los valores del CHECK constraint
    if body.motivo_reprogramacion is not None:
        if body.motivo_reprogramacion not in MOTIVOS_REPROGRAMACION:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"El motivo '{body.motivo_reprogramacion}' no es valido. "
                    f"Valores permitidos: {', '.join(MOTIVOS_REPROGRAMACION)}"
                ),
            )

    # Validamos tipo_modificacion contra los valores permitidos
    if body.tipo_modificacion is not None:
        if body.tipo_modificacion not in TIPOS_MODIFICACION_PATCH:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"El tipo_modificacion '{body.tipo_modificacion}' no es valido. "
                    f"Valores permitidos: {', '.join(TIPOS_MODIFICACION_PATCH)}"
                ),
            )

    # Guardamos el tecnico anterior antes de actualizar (para el historial en BD)
    tecnico_anterior = orden.get("tecnico_id")

    # Actualizamos la OT en memoria
    orden["tecnico_id"] = body.tecnico_id

    if body.tecnico_id is None:
        # OT descartada: vuelve a estado por_asignar
        orden["estado"] = "por_asignar"
    elif orden["estado"] in ("por_revisar", "por_asignar"):
        # Asignacion nueva: avanza al siguiente estado logico
        orden["estado"] = "asignacion_por_confirmar"

    # --- Persistir en PostgreSQL (cada evento es una fila nueva) ---
    guardado_en_bd = False
    db_error = None
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Construir fecha_orden_de_trabajo desde los datos de la OT
        fecha_ot = None
        if orden.get("fecha_programada") and orden.get("hora_programada"):
            hora = orden["hora_programada"]
            if hora.count(":") == 1:
                hora += ":00"
            fecha_ot = f"{orden['fecha_programada']}T{hora}"

        # id_propuesta: tecnico que tenia la OT antes del cambio
        # (puede ser None si la OT nunca fue asignada — la columna es nullable)
        id_propuesta = tecnico_anterior

        # usuario_dispatcher desde revisado_por (si viene)
        usuario_dispatcher = (
            body.revisado_por.nombre if body.revisado_por else None
        )

        # tipo_modificacion y propuesta_modificada
        es_reprogramacion = body.motivo_reprogramacion is not None
        tipo_mod = body.tipo_modificacion  # valor directo del frontend

        # INSERT: siempre una fila nueva (historial de eventos, nunca se sobrescribe)
        cur.execute(
            """
            INSERT INTO asignacion (
                id_orden_trabajo, id_propuesta, id_aceptada,
                fecha_asignacion, fecha_orden_de_trabajo,
                motivo_reprogramacion, usuario_dispatcher,
                fecha_generacion, propuesta_modificada,
                tipo_modificacion
            ) VALUES (
                %s, %s, %s, NOW(), %s, %s, %s, NOW(), %s, %s
            )
            """,
            (
                id,
                id_propuesta,              # tecnico anterior (o el nuevo si no habia)
                body.tecnico_id,           # tecnico nuevo (o null si descartada)
                fecha_ot,
                body.motivo_reprogramacion,
                usuario_dispatcher,
                es_reprogramacion,         # propuesta_modificada
                tipo_mod,
            ),
        )

        conn.commit()
        guardado_en_bd = True
        cur.close()
    except Exception as e:
        db_error = str(e)
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    respuesta = {**orden, "guardado_en_bd": guardado_en_bd}
    if db_error:
        respuesta["db_error"] = db_error

    return respuesta


# --- Asignacion Masiva de Tecnicos ---

@app.post(
    "/api/asignar-tecnicos",
    tags=["Ordenes de Trabajo"],
    summary="Asignar tecnicos a OTs de forma masiva desde una corrida de optimizacion",
    response_description="Resumen de la asignacion con detalle de OTs actualizadas y errores.",
)
def asignar_tecnicos_masivo(body: AsignarTecnicosRequest):
    """
    Recibe el resultado de una corrida de optimizacion revisada por un
    dispatcher/coordinador y aplica las asignaciones de tecnicos.

    **Procesamiento por cada ruta recibida:**
    1. Valida que el tecnico exista en el sistema.
    2. Para cada OT en `ruta_final`:
       - Actualiza `tecnico_id` y `estado` en la base de datos en memoria.
       - Prepara un registro para insertar en la tabla `asignacion` de PostgreSQL.
    3. Inserta los registros exitosos en la base de datos de Render.

    **Estrategia parcial:** las asignaciones validas se aplican y los errores
    se reportan sin detener el procesamiento del resto.

    **Body esperado:** JSON con la estructura completa de la corrida
    (fecha_planificacion, revisado_por, rutas, pendientes, etc.).
    """
    actualizadas = []
    errores = []
    registros_db = []

    # Mapa de propuestas: ot_id -> tecnico_id que lo tenia en ruta_propuesta
    propuesta_map: dict[str, str] = {}
    for ruta in body.rutas:
        for ot_id in ruta.ruta_propuesta:
            propuesta_map[ot_id] = ruta.tecnico_id

    # --- Procesar cada ruta ---
    for ruta in body.rutas:
        tecnico_id = ruta.tecnico_id

        # Validar que el tecnico exista en la BD en memoria
        tecnico = next((t for t in DB_TECNICOS if t["id"] == tecnico_id), None)
        if tecnico is None:
            for ot_id in ruta.ruta_final:
                errores.append({
                    "ot_id": ot_id,
                    "error": f"Tecnico con id '{tecnico_id}' no encontrado en el sistema.",
                })
            continue

        for ot_id in ruta.ruta_final:
            # Buscar la OT en memoria
            orden = next((o for o in DB_ORDENES if o["id"] == ot_id), None)
            if orden is None:
                errores.append({
                    "ot_id": ot_id,
                    "error": f"OT '{ot_id}' no encontrada en el sistema.",
                })
                continue

            # Actualizar la OT en memoria
            orden["tecnico_id"] = tecnico_id
            if orden["estado"] in ("por_revisar", "por_asignar"):
                orden["estado"] = "asignacion_por_confirmar"

            actualizadas.append({
                "ot_id": ot_id,
                "tecnico_id": tecnico_id,
                "estado": orden["estado"],
            })

            # Construir fecha_orden_de_trabajo desde los datos de la OT
            fecha_ot = None
            if orden.get("fecha_programada") and orden.get("hora_programada"):
                hora = orden["hora_programada"]
                if hora.count(":") == 1:
                    hora += ":00"
                fecha_ot = f"{orden['fecha_programada']}T{hora}"

            # Determinar si la propuesta fue modificada y el tipo
            propuesta_modificada = not ruta.aceptada_sin_modificacion
            tipo_modificacion = None
            if ruta.modificaciones:
                tipo_modificacion = json.dumps(
                    ruta.modificaciones, ensure_ascii=False
                )[:100]

            registros_db.append({
                "id_orden_trabajo": ot_id,
                "id_propuesta": propuesta_map.get(ot_id),
                "id_aceptada": tecnico_id,
                "fecha_asignacion": body.revisado_en,
                "fecha_orden_de_trabajo": fecha_ot,
                "motivo_reprogramacion": None,
                "usuario_dispatcher": body.revisado_por.nombre,
                "fecha_generacion": body.generado_en,
                "propuesta_modificada": propuesta_modificada,
                "tipo_modificacion": tipo_modificacion,
            })

    # --- Insertar en PostgreSQL ---
    db_resultado = {"insertados": 0, "error": None}
    if registros_db:
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            for reg in registros_db:
                cur.execute(
                    """
                    INSERT INTO asignacion (
                        id_orden_trabajo, id_propuesta, id_aceptada,
                        fecha_asignacion, fecha_orden_de_trabajo,
                        motivo_reprogramacion, usuario_dispatcher,
                        fecha_generacion, propuesta_modificada,
                        tipo_modificacion
                    ) VALUES (
                        %(id_orden_trabajo)s, %(id_propuesta)s, %(id_aceptada)s,
                        %(fecha_asignacion)s, %(fecha_orden_de_trabajo)s,
                        %(motivo_reprogramacion)s, %(usuario_dispatcher)s,
                        %(fecha_generacion)s, %(propuesta_modificada)s,
                        %(tipo_modificacion)s
                    )
                    """,
                    reg,
                )
            conn.commit()
            db_resultado["insertados"] = len(registros_db)
            cur.close()
        except Exception as e:
            db_resultado["error"] = str(e)
            if conn:
                try:
                    conn.rollback()
                except Exception:
                    pass
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    return {
        "mensaje": "Asignacion masiva completada.",
        "fecha_planificacion": body.fecha_planificacion,
        "revisado_por": body.revisado_por.nombre,
        "total_recibidas": sum(len(r.ruta_final) for r in body.rutas),
        "total_actualizadas": len(actualizadas),
        "actualizadas": actualizadas,
        "errores": errores,
        "base_de_datos": db_resultado,
    }


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
