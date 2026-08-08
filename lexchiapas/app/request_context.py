import contextvars
import logging

# BUG REAL (auditoria de salud del backend, 2026-08-06, hallazgo M2): sin
# esto, no habia forma de correlacionar los logs de un mismo request/turno
# de chat -- con multiples llamadas LLM/DB por turno (embed -> decidir ->
# buscar -> rerank -> generar -> segundo gate de grounding), cuando algo
# fallaba a mitad de camino no habia forma de agrupar esos logs sin adivinar
# por timestamp. contextvars se propaga automaticamente a traves de
# asyncio.to_thread (copia el context al despachar al thread) y de
# asyncio.create_task (copia el context al momento de crear el Task) -- asi
# que el mismo request_id aparece tanto en los logs sincronos del pipeline
# (que corren en un thread aparte, ver app.bots.telegram_bot) como en el
# procesamiento en background del webhook de Telegram (ver
# app.api.telegram_webhook, hallazgo A2).
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class RequestIdLogFilter(logging.Filter):
    """Inyecta el request_id actual (o "-" fuera de un request) en cada
    LogRecord como record.request_id, para poder incluirlo en el formato de
    logging.basicConfig (ver app/main.py). Debe agregarse al HANDLER, no al
    logger raiz -- un Filter en el logger raiz solo corre para records que
    se originan ahi mismo, no para los que suben desde loggers hijos
    (app.rag.*, app.bots.*, etc.) durante la propagacion normal."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True
