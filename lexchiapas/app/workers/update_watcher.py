"""Vigilante de leyes (LexChiapas_Plan_Agente_Investigacion.md, 6.7 y 10.0e).

SOLO DETECTA: compara el catalogo vigente de las fuentes (Congreso y Consejeria)
contra los documentos activos y avisa por Telegram. No descarga PDFs ni
reingiere nada: toda recarga pasa por revision humana (ingestion-dedupe,
comparacion de articulos, regresion). Reutiliza el matching verificado de
update_tasks (nombre normalizado + URL normalizada) y la alerta de
alerting_tasks.
"""

import json
import logging

from app.database import SessionLocal
from app.models import Document
from app.workers.alerting_tasks import _get_redis_client, send_admin_telegram_alert
from app.workers.celery_app import celery_app
from app.workers.update_tasks import (
    _guess_source,
    _normalize_name,
    _normalize_url_for_comparison,
)
from ingestion.scrapers import congreso_scraper, consejeria_scraper

logger = logging.getLogger("lexchiapas.update_watcher")

_CATALOG_SNAPSHOT_KEY = "law_watcher:catalog_names"
_MAX_NAMES_IN_ALERT = 8


def _matches(document_nombre: str, laws: list[dict]) -> list[dict]:
    """Entradas del catalogo cuyo nombre normalizado contiene al del documento
    o viceversa (mismo criterio que update_tasks._find_match)."""
    normalized_doc = _normalize_name(document_nombre)
    found = []
    for law in laws:
        normalized_law = _normalize_name(law.get("nombre", ""))
        if normalized_law and (normalized_doc in normalized_law or normalized_law in normalized_doc):
            found.append(law)
    return found


def _is_not_a_current_law(normalized_name: str) -> bool:
    return "ABROGAD" in normalized_name or normalized_name.startswith("DECLARATORIA")


def detect_updates(documents: list[dict], catalogs: dict[str, list[dict]]) -> dict:
    """Funcion pura. `documents`: [{id, nombre, source_url}] activos.
    `catalogs`: {"congreso": [...], "consejeria": [...]} con [{nombre, source_url}].

    Devuelve:
    - changed: documentos con nombre sin ambiguedad y URL distinta (mas alla de
      host/encoding) dentro de su misma fuente -> candidatos a reforma.
    - unmatched: documentos de fuente conocida sin entrada (sin_match) o con
      mas de una (ambiguo) en el catalogo actual.
    - unknown_source: documentos cuyo source_url no es de una fuente conocida.
    - new_laws: entradas del catalogo que no corresponden a ningun documento
      activo (leyes que aun no se cargaron).
    """
    changed, unmatched, unknown_source = [], [], []
    for doc in documents:
        source = _guess_source(doc.get("source_url"))
        if source is None:
            unknown_source.append(doc["nombre"])
            continue
        found = _matches(doc["nombre"], catalogs.get(source, []))
        if len(found) != 1:
            unmatched.append({"nombre": doc["nombre"], "source": source, "reason": "ambiguo" if found else "sin_match"})
            continue
        new_url = found[0]["source_url"]
        if _normalize_url_for_comparison(new_url) != _normalize_url_for_comparison(doc["source_url"]):
            changed.append({"document_id": doc["id"], "nombre": doc["nombre"], "source": source,
                            "old_url": doc["source_url"], "new_url": new_url})

    # Leyes nuevas: solo contra el catalogo del Congreso (fuente primaria; el de
    # Consejeria repite casi todo con otros nombres), sin duplicados por nombre
    # normalizado y sin abrogadas ni declaratorias, que no son leyes vigentes.
    new_laws, seen = [], set()
    doc_names = [_normalize_name(d["nombre"]) for d in documents]
    for law in catalogs.get("congreso", []):
        normalized_law = _normalize_name(law.get("nombre", ""))
        if not normalized_law or normalized_law in seen or _is_not_a_current_law(normalized_law):
            continue
        seen.add(normalized_law)
        if not any(d in normalized_law or normalized_law in d for d in doc_names):
            new_laws.append({"nombre": law["nombre"], "source": "congreso", "source_url": law.get("source_url")})
    return {"changed": changed, "unmatched": unmatched, "unknown_source": unknown_source, "new_laws": new_laws}


def _names_preview(names: list[str]) -> str:
    shown = names[:_MAX_NAMES_IN_ALERT]
    extra = len(names) - len(shown)
    return "; ".join(shown) + (f" (y {extra} mas)" if extra > 0 else "")


def build_alert(report: dict, new_since_last: list[str] | None) -> str | None:
    """Texto de la alerta, o None si no hay nada que avisar. `new_since_last`
    es None en la primera corrida (solo se fija la linea base del catalogo)."""
    lines = []
    if report["changed"]:
        lines.append(f"{len(report['changed'])} ley(es) cargada(s) con URL nueva en la fuente: "
                     + _names_preview([c["nombre"] for c in report["changed"]]))
    if new_since_last:
        lines.append(f"{len(new_since_last)} ley(es) nueva(s) en el catalogo desde la ultima revision: "
                     + _names_preview(new_since_last))
    if not lines:
        return None
    return ("Vigilante de leyes: " + " | ".join(lines)
            + ". No se actualizo nada: revisar con ingestion-dedupe y recargar a mano.")


def _load_documents() -> list[dict]:
    db = SessionLocal()
    try:
        rows = db.query(Document.id, Document.nombre, Document.source_url).filter(Document.is_active.is_(True)).all()
        return [{"id": r.id, "nombre": r.nombre, "source_url": r.source_url} for r in rows]
    finally:
        db.close()


@celery_app.task(name="app.workers.update_watcher.law_update_watcher")
def law_update_watcher() -> dict:
    """Semanal. No modifica la base ni descarga PDFs. Devuelve el reporte
    resumido y avisa por Telegram solo si hay cambios o leyes nuevas."""
    documents = _load_documents()
    catalogs: dict[str, list[dict]] = {}
    errors: list[str] = []
    for source, scraper in (("congreso", congreso_scraper), ("consejeria", consejeria_scraper)):
        needed = any(_guess_source(d["source_url"]) == source for d in documents)
        if not needed:
            continue
        try:
            catalogs[source] = scraper.list_available_laws()
        except Exception as exc:  # noqa: BLE001 - una fuente caida no debe ocultar la otra
            errors.append(f"{source}: {exc}")
            logger.warning("law_update_watcher: no se pudo listar %s: %s", source, exc)

    report = detect_updates(documents, catalogs)

    # Linea base del catalogo para avisar solo de leyes nuevas desde la ultima corrida.
    current_names = sorted({" ".join(law["nombre"].split()) for law in catalogs.get("congreso", [])})
    new_since_last: list[str] | None = None
    if current_names and not errors:
        try:
            redis_client = _get_redis_client()
            previous_raw = redis_client.get(_CATALOG_SNAPSHOT_KEY)
            if previous_raw is not None:
                previous = set(json.loads(previous_raw))
                new_since_last = sorted(n for n in current_names if n not in previous)
            redis_client.set(_CATALOG_SNAPSHOT_KEY, json.dumps(current_names))
        except Exception as exc:  # noqa: BLE001 - sin Redis no hay linea base, solo se pierde el aviso de nuevas
            logger.warning("law_update_watcher: snapshot en Redis fallo: %s", exc)

    alert = build_alert(report, new_since_last)
    alerted = send_admin_telegram_alert(alert) if alert else False
    return {
        "checked": len(documents),
        "changed": [c["nombre"] for c in report["changed"]],
        "unmatched": len(report["unmatched"]),
        "new_laws_in_catalog": len(report["new_laws"]),
        "new_since_last": new_since_last,
        "alerted": alerted,
        "errors": errors,
    }
