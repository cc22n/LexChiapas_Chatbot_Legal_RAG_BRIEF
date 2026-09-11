import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.request_context import RequestIdLogFilter, request_id_var

# BUG REAL (auditoria de salud del backend, 2026-08-06, hallazgo M1): sin
# esto, el root logger de Python no tiene ningun handler configurado bajo
# uvicorn (uvicorn solo configura SUS PROPIOS loggers -- "uvicorn",
# "uvicorn.access", "uvicorn.error" -- nunca el root). Los ~30 `logger =
# logging.getLogger("lexchiapas.xxx")` de app/rag, app/bots, app/llm, etc.
# heredan de un root sin handlers: Python cae al "last resort handler"
# (stderr, nivel WARNING), asi que TODO logger.info/debug se perdia en
# silencio -- incluidas trazas reales como la decision del agente o hits de
# semantic_cache. Debe correr ANTES de importar app.api (algunos modulos,
# ej. telegram_webhook, ya loguean un warning al importarse).
#
# El handler explicito (en vez de dejar que basicConfig cree el suyo) es
# para poder colgarle RequestIdLogFilter (hallazgo M2) -- un Filter agregado
# al logger raiz NO corre para records que se originan en loggers hijos
# (app.rag.*, etc.), tiene que ir en el handler. %(request_id)s en el
# formato queda como "-" para logs que no ocurren dentro de un request HTTP
# (arranque del proceso, tasks de Celery).
_log_handler = logging.StreamHandler()
_log_handler.addFilter(RequestIdLogFilter())
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s",
    handlers=[_log_handler],
)

from app.api import admin, chat_web, feedback, health, public, telegram_webhook, whatsapp_webhook
from app.config import get_settings

app = FastAPI(title="LexChiapas", description="Chatbot legal RAG sobre leyes de Chiapas")

logger = logging.getLogger("lexchiapas.main")


@app.exception_handler(Exception)
async def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
    """BUG REAL (auditoria de salud del backend, 2026-08-06, hallazgo B1):
    sin un handler global, una excepcion no controlada en cualquier
    endpoint que NO sea /api/chat/web (que ya esta blindado por
    app.bots.conversation_store.handle_turn con el mismo patron que este
    handler generaliza) caia al 500 generico de Starlette -- texto plano
    "Internal Server Error", sin JSON, sin request_id -- mientras que
    errores de validacion/auth si devuelven JSON estructurado. No cambia
    que se expone al cliente (nunca se mando el traceback real, debug=False
    es el default sin sobreescribir), solo unifica el formato y asegura que
    el traceback SI quede en el log del servidor con su request_id.

    request_id sale de request.state, NO del contextvar request_id_var --
    BUG REAL encontrado al escribir el test de este handler: ServerErrorMiddleware
    (que invoca este handler) esta POR ENCIMA de add_request_id en el stack de
    middleware, y para cuando una excepcion llega hasta aca, el `finally` de
    add_request_id YA corrio y ya hizo request_id_var.reset(token) -- el
    contextvar volveria a leer "-" justo en el peor momento (el log de la
    excepcion real). request.state SI sobrevive: esta respaldado por el scope
    ASGI compartido, no por el contextvar que un middleware de mas abajo ya
    limpio en su camino de salida."""
    request_id = getattr(request.state, "request_id", None) or request_id_var.get()
    logger.exception(
        "Excepcion no manejada en %s %s (request_id=%s)", request.method, request.url.path, request_id, exc_info=exc
    )
    return JSONResponse({"detail": "internal error", "request_id": request_id}, status_code=500)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """BUG REAL (hallazgo M2): ver docstring de app.request_context --
    genera un UUID propio por request en vez de confiar en un X-Request-ID
    entrante del cliente (evitaria que un cliente externo inyecte valores
    arbitrarios en los logs del servidor). Se guarda TANTO en el contextvar
    (para RequestIdLogFilter, ver app.request_context -- cubre los logs
    normales de un request, incluidos los que corren en threads via
    asyncio.to_thread) COMO en request.state (para handle_unexpected_exception,
    ver su docstring sobre por que el contextvar solo no alcanza ahi)."""
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
    finally:
        request_id_var.reset(token)


# Generoso a proposito: el payload real mas grande de este backend es
# WebChatRequest.message (max_length=2000 caracteres, ver app/schemas/chat.py)
# mas metadata chica -- no hay ningun endpoint que reciba archivos o texto
# largo por HTTP (la ingesta de leyes corre via scripts/Celery, no por API).
MAX_BODY_SIZE_BYTES = 1_000_000


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """BUG REAL (auditoria de salud del backend, 2026-08-06, hallazgo M5):
    sin esto, Starlette lee el body completo en memoria ANTES de que
    Pydantic pueda rechazar por max_length -- un POST con un body JSON
    gigante fuerza esa lectura completa igual, aunque el campo individual
    este limitado. Rechaza por el header Content-Length (rapido, sin leer
    el body) cuando esta presente; si el cliente no lo manda (chunked
    transfer encoding), no hay forma de saber el tamano de antemano sin
    leer -- ese caso queda fuera del alcance de este check, mitigado igual
    por el rate limiting existente."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            too_large = int(content_length) > MAX_BODY_SIZE_BYTES
        except ValueError:
            too_large = False
        if too_large:
            return JSONResponse({"detail": "payload demasiado grande"}, status_code=413)
    return await call_next(request)


settings = get_settings()

# Fase 9.8/A4: headers de seguridad. Ausentes por completo hasta ahora (el
# frontend Next.js pone los suyos via next.config.ts). Para una API JSON el
# valor principal es HSTS + anti-sniffing + anti-clickjacking; la CSP estricta
# aplica a las respuestas JSON pero se exceptua en /docs|/redoc|/openapi.json,
# que SI sirven HTML+scripts de CDN (Swagger UI) y una CSP default-src 'none'
# los romperia.
_DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    if not request.url.path.startswith(_DOCS_PATHS):
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        )
    # HSTS solo fuera de development: en local se sirve por HTTP (el navegador
    # igual lo ignoraria) y encenderlo podria fijar HSTS para localhost.
    if settings.environment != "development":
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


allowed_origins = []
if settings.frontend_origin:
    # Si FRONTEND_ORIGIN esta definido en .env, se usa ese origen especifico.
    allowed_origins = [settings.frontend_origin]
    # BUG REAL (2026-07-30): en development, localhost y 127.0.0.1 son
    # origenes DISTINTOS para el navegador aunque apunten a la misma
    # maquina/puerto -- un FRONTEND_ORIGIN de un solo valor no puede
    # satisfacer ambos. Esto causo que 2 sesiones de trabajo distintas se
    # pisaran el valor entre si (una lo puso en 127.0.0.1 probando en
    # navegador real, otra lo puso en localhost probando lo mismo) porque
    # cada una veia funcionar SU variante y romperse la otra. Se acepta la
    # variante hermana automaticamente solo en development -- production
    # sigue exigiendo match exacto de FRONTEND_ORIGIN (ej. la URL real de
    # Vercel), sin aflojar esa politica.
    if settings.environment == "development":
        if "://localhost:" in settings.frontend_origin:
            allowed_origins.append(settings.frontend_origin.replace("://localhost:", "://127.0.0.1:"))
        elif "://127.0.0.1:" in settings.frontend_origin:
            allowed_origins.append(settings.frontend_origin.replace("://127.0.0.1:", "://localhost:"))
elif settings.environment == "development":
    # Si no, y estamos en modo desarrollo, permitir cualquier origen.
    # Esto es conveniente para desarrollo local con un frontend en un puerto diferente.
    allowed_origins = ["*"]

if allowed_origins:
    # BUG REAL (2026-08-04, revision de seguridad): allow_credentials=True
    # incondicional, incluso cuando allowed_origins=["*"] (caso dev sin
    # FRONTEND_ORIGIN configurado). Starlette, ante ["*"] + credentials=True,
    # NO manda literalmente "*" -- refleja el Origin real de cada request
    # (unico modo de cumplir la spec CORS, que prohibe combinar wildcard con
    # credentials), asi que en la practica CUALQUIER origen podia hacer
    # requests con cookies incluidas. Hoy el unico endpoint que de verdad usa
    # cookies es /admin/* (via la cookie que emite POST /admin/login, ver
    # admin.py) -- /api/chat/web y los webhooks no la necesitan. Regla
    # aplicada: credentials solo se habilitan cuando el origen es especifico
    # y conocido (FRONTEND_ORIGIN configurado), nunca en modo wildcard.
    allow_credentials = allowed_origins != ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health.router)
app.include_router(telegram_webhook.router)
app.include_router(whatsapp_webhook.router)
app.include_router(admin.router)
app.include_router(chat_web.router)
app.include_router(feedback.router)
app.include_router(public.router)
