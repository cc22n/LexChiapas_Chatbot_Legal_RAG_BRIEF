"""Rutas del agente y parseo de la decision del nodo "decidir". Funciones puras,
sin acceso a BD ni a LLM; agent_pipeline.py las re-exporta con los mismos
nombres (los tests importan de ahi)."""

import json
import re
from enum import StrEnum

class Ruta(StrEnum):
    """Rutas que puede decidir el nodo "decidir". Los valores son las mismas
    cadenas de siempre (prompt, tests y logs no cambian); StrEnum compara igual
    que str."""

    NINGUNA = "ninguna"
    BUSQUEDA_GENERAL = "busqueda_general"
    BUSQUEDA_POR_LEY = "busqueda_por_ley"
    ARTICULO_ESPECIFICO = "articulo_especifico"
    HISTORIAL_LEY = "historial_ley"


_VALID_DECISIONS = {r.value for r in Ruta}
_NULLISH = {"NINGUNA", "NINGUNO", "N/A", "-", ""}

_ACCION_RE = re.compile(r"ACCION\s*:\s*(\S+)", re.IGNORECASE)
_LEY_RE = re.compile(r"LEY\s*:\s*(.+)", re.IGNORECASE)
_ARTICULO_RE = re.compile(r"ARTICULO\s*:\s*(.+)", re.IGNORECASE)


def _normalize_decision_fields(
    accion_raw: object, ley_raw: object, articulo_raw: object
) -> tuple[str, str | None, str | None] | None:
    """Normaliza y valida los 3 campos crudos (accion/ley/articulo) sin
    importar si vinieron del parser JSON o del parser regex de texto plano
    (ver _parse_decision_json/_parse_decision abajo) -- misma logica de
    downgrades seguros y de tolerancia a sufijos de articulo, centralizada
    aca para que los dos caminos de parseo no puedan divergir. Devuelve None
    si `accion_raw` no es una de las 5 acciones validas -- el llamador debe
    caer al default seguro (busqueda_general) en ese caso, nunca bloquear ni
    asumir NINGUNA."""
    if not accion_raw:
        return None
    accion = str(accion_raw).strip().lower().rstrip(".,;")
    if accion not in _VALID_DECISIONS:
        return None

    ley = str(ley_raw).strip() if ley_raw else None
    if ley and ley.upper() in _NULLISH:
        ley = None

    articulo = None
    if articulo_raw:
        articulo_clean = str(articulo_raw).strip().rstrip(".,;")
        if articulo_clean and articulo_clean.upper() not in _NULLISH:
            # Bug real encontrado y corregido (Etapa 1, ver app.rag.chunker.py
            # ARTICULO_RE para el mismo patron ya conocido): chunks.articulo_numero
            # guarda el sufijo latino cuando el articulo lo tiene ("15 Bis", "117
            # BIS", "278-A") -- son comunes en este corpus (Codigo Penal en
            # particular tiene muchos). Extraer SOLO el digito inicial (version
            # anterior de este parser) descartaba el sufijo, asi que
            # get_article() nunca encontraba estos articulos aunque existieran
            # de verdad -- un "articulo_especifico" pedido con sufijo siempre
            # caia a "no encontrado". Se preserva el numero completo (digitos +
            # sufijo/guion tal como lo escribio el LLM); get_article() compara
            # sin distinguir mayusculas/espacios para tolerar variantes de
            # formato ("15 Bis" vs "15 BIS").
            match = re.search(r"\d+[\s-]?[A-Za-z]*", articulo_clean)
            if match:
                articulo = match.group(0).strip()

    # Downgrades seguros: si la accion pedida no trae los datos que
    # necesita, se cae a busqueda_general en vez de fallar o de forzar una
    # busqueda con datos incompletos (ver docstring de modulo, invariante 2).
    if accion == Ruta.BUSQUEDA_POR_LEY and not ley:
        accion = Ruta.BUSQUEDA_GENERAL
    if accion == Ruta.ARTICULO_ESPECIFICO and not (ley and articulo):
        accion = Ruta.BUSQUEDA_GENERAL
    if accion == Ruta.HISTORIAL_LEY and not ley:
        accion = Ruta.BUSQUEDA_GENERAL

    return accion, ley, articulo


def _parse_decision_json(raw: str) -> tuple[str, str | None, str | None] | None:
    """Parsea el output de DECIDE_SYSTEM_PROMPT como JSON
    {"accion", "ley", "articulo"} -- se intenta PRIMERO (ver _node_decidir,
    que pide response_format={"type":"json_object"}). Devuelve None si `raw`
    no es JSON valido o no tiene forma de objeto -- el llamador cae a
    _parse_decision (regex sobre texto plano) en ese caso, para el proveedor
    que ignore response_format y devuelva texto plano de todas formas."""
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    return _normalize_decision_fields(data.get("accion"), data.get("ley"), data.get("articulo"))


def _parse_decision(raw: str) -> tuple[str, str | None, str | None] | None:
    """Parsea el output de DECIDE_SYSTEM_PROMPT en el formato de texto plano
    ACCION:/LEY:/ARTICULO: -- red de seguridad para cuando el proveedor no
    respeta response_format (ver _parse_decision_json, que se intenta
    primero en _node_decidir). Devuelve (accion, ley_o_None, articulo_o_None),
    o None si no se pudo parsear una accion valida."""
    accion_match = _ACCION_RE.search(raw)
    ley_match = _LEY_RE.search(raw)
    articulo_match = _ARTICULO_RE.search(raw)
    return _normalize_decision_fields(
        accion_match.group(1) if accion_match else None,
        ley_match.group(1) if ley_match else None,
        articulo_match.group(1) if articulo_match else None,
    )
