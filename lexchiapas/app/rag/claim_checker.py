"""Claim-checker por afirmacion (idea 2 de 4 de la sesion de brainstorming
con Perplexity, 2026-08-11 -- ver LexChiapas_Plan_Futuro.md Fase 9.2).

DISTINTO del segundo gate de grounding ya existente
(app.rag.grounding.answer_is_grounded_in_practice), que juzga la respuesta
ENTERA de una sola vez ("¿esto en general tiene base real?"). Este modulo
baja ese juicio a nivel de afirmacion individual: descompone la respuesta
en sus afirmaciones materiales y dice, PARA CADA UNA, si esta respaldada
por un fragmento especifico o no.

DECISION DE DISENO DELIBERADA: esto NO reemplaza ni gatea el pipeline real
todavia (no se llama desde rag_pipeline.py ni agent_pipeline.py). Es una
herramienta de MEDICION -- el gate que ya esta en produccion (grounding.py)
llego a 21/2/1 en el golden dataset real y no tiene evidencia de falsos
positivos conocidos; reemplazarlo por un contrato distinto ("lista de
afirmaciones" en vez de "un booleano") sin medir primero seria repetir el
error que este proyecto evita a proposito con todo lo demas (HyDE,
reranker, agentic_rag: se miden antes de activarse por defecto). Usar este
modulo para auditar respuestas ya generadas (via un script puntual o un
endpoint de admin futuro) y decidir con evidencia real si vale la pena
integrarlo como gate.
"""

import json
import logging
from dataclasses import dataclass

from app.llm.router import AllModelsFailedError, generate_with_fallback
from app.rag.retriever import RetrievedChunk

logger = logging.getLogger("lexchiapas.claim_checker")

CLAIM_CHECKER_SYSTEM_PROMPT = (
    "Descompones una respuesta legal en sus afirmaciones MATERIALES -- "
    "hechos o consecuencias juridicas concretas que el usuario podria "
    "verificar o citar. NO cuentes como afirmacion material: saludos, "
    "conectores, el disclaimer final ('esto no sustituye asesoria legal'), "
    "ni frases que solo resumen o introducen lo que sigue. "
    "Para CADA afirmacion material, decide si esta respaldada DIRECTAMENTE "
    "por el contenido de alguno de los fragmentos legales numerados que se "
    "te dan -- no por sentido comun, no por inferencia mas alla de lo "
    "escrito en el fragmento. "
    "Responde SOLO con un objeto JSON, sin markdown, con esta forma exacta: "
    '{"claims": [{"texto": "...", "respaldado": true|false, "fragmento": N|null}]}. '
    "fragmento es el numero (1-indexado) del fragmento que respalda esa "
    "afirmacion especifica, o null si respaldado=false o si la afirmacion "
    "no requiere una cita puntual (ej. 'no encontre informacion sobre X')."
)


@dataclass(frozen=True)
class ClaimCheck:
    texto: str
    respaldado: bool
    fragmento_index: int | None
    """1-indexado, referencia a la posicion en la lista de chunks pasada a
    check_claims -- None si no aplica o si el proveedor no lo especifico."""


def _format_chunks_numbered(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "(sin fragmentos)"
    return "\n\n".join(
        f"[{i}] {c.document_nombre}, Articulo {c.articulo_numero}\n{c.content}"
        for i, c in enumerate(chunks, start=1)
    )


def check_claims(
    question: str, answer_text: str, retrieved_chunks: list[RetrievedChunk]
) -> list[ClaimCheck] | None:
    """Devuelve la lista de afirmaciones detectadas en `answer_text` con su
    veredicto de respaldo, o None si la llamada fallo por cualquier motivo
    (todos los proveedores caidos, JSON invalido, etc.) -- mismo principio
    de fallback seguro que el resto del pipeline (nunca bloquear ni alterar
    una respuesta ya generada por la falla de una herramienta de medicion
    auxiliar). None es distinto de `[]`: `[]` significa "se evaluo y no se
    encontraron afirmaciones materiales", None significa "no se pudo
    evaluar"."""
    messages = [
        {"role": "system", "content": CLAIM_CHECKER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"Pregunta del usuario: {question}\n\n"
                f"Fragmentos legales recuperados:\n{_format_chunks_numbered(retrieved_chunks)}\n\n"
                f"Respuesta generada: {answer_text}"
            ),
        },
    ]
    try:
        raw, model_used, _, _ = generate_with_fallback(
            messages, temperature=0.0, fast=True, response_format={"type": "json_object"}
        )
        parsed = json.loads(raw)
        claims_raw = parsed.get("claims", [])
        claims = [
            ClaimCheck(
                texto=c.get("texto", ""),
                respaldado=bool(c.get("respaldado", False)),
                fragmento_index=c.get("fragmento"),
            )
            for c in claims_raw
        ]
        logger.info(
            "claim_checker (%s): %d afirmaciones, %d respaldadas para pregunta=%r",
            model_used,
            len(claims),
            sum(1 for c in claims if c.respaldado),
            question,
        )
        return claims
    except AllModelsFailedError as exc:
        logger.warning("claim_checker: todos los proveedores fallaron: %s", exc)
        return None
    except (json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        logger.warning("claim_checker: respuesta no parseable como JSON esperado: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001 - fallback silencioso, ver docstring
        logger.warning("claim_checker fallo (error inesperado): %s", exc)
        return None
