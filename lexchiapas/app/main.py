from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, chat_web, feedback, health, public, telegram_webhook, whatsapp_webhook
from app.config import get_settings

app = FastAPI(title="LexChiapas", description="Chatbot legal RAG sobre leyes de Chiapas")

settings = get_settings()

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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
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
