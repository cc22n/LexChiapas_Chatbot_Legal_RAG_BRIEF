"""Endpoints PUBLICOS (sin auth, mismo nivel que POST /api/chat/web) para el
explorador visual de leyes/relaciones legales (WEB_FRONTEND_PLAN.md Fase G).

No reimplementa la logica de query_graph (app.rag.agent_tools) ni de
fuzzy_ilike_pattern (app.rag.retriever) -- las reusa tal cual, mismo
criterio que agent_tools ya reusa hybrid_search/rerank en vez de duplicar
retrieval.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import get_db
from app.rag.agent_tools import query_graph
from app.rag.retriever import fuzzy_ilike_pattern

router = APIRouter(prefix="/api", tags=["public"])


@router.get("/laws")
def list_laws(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(
        text("SELECT id, nombre FROM documents WHERE is_active = true ORDER BY nombre")
    ).mappings().all()
    return [dict(r) for r in rows]


@router.get("/legal-relations")
def legal_relations(law: str, db: Session = Depends(get_db)) -> dict:
    """Explorador hub-and-spoke: para la ley pedida, devuelve la "otra ley"
    involucrada en cada relacion real (legal_relations, via query_graph),
    sin importar de que lado (from/to) aparece la ley consultada en la fila
    original -- ver instrucciones de la tarea para el razonamiento completo
    de la direccion semantica.

    Si `law` no matchea ningun documento activo, devuelve igual
    {"law": law, "relations": []} con status 200 (no 404) -- mismo
    comportamiento honesto "no hay datos" que query_graph ya documenta,
    no una falla.
    """
    pattern = fuzzy_ilike_pattern(law)
    canonical_row = db.execute(
        text("SELECT nombre FROM documents WHERE is_active = true AND nombre ILIKE :pattern LIMIT 1"),
        {"pattern": pattern},
    ).first()

    if canonical_row is None:
        return {"law": law, "relations": []}

    canonical_name = canonical_row.nombre

    raw_relations = query_graph(db, law_name=law)

    relations = []
    for rel in raw_relations:
        if rel["from_document_nombre"].strip().casefold() == canonical_name.strip().casefold():
            # La ley consultada es el ORIGEN de esta relacion -- el "otro
            # lado" es to_law_name_raw (la ley que query_graph ya identifico).
            to_law_name = rel["to_law_name_raw"]
        else:
            # La ley consultada aparece del lado to_document_id (otra ley la
            # reformo/derogo/adiciono) -- el "otro lado" real es quien SI
            # hizo el cambio, from_document_nombre.
            to_law_name = rel["from_document_nombre"]

        relations.append(
            {
                "relation_type": rel["relation_type"],
                "to_law_name": to_law_name,
                "to_document_id": rel["to_document_id"],
                "articulo": rel["from_articulo"],
                "fecha": rel["fecha"].isoformat() if rel["fecha"] else None,
                "source_text": rel["source_text"],
            }
        )

    return {"law": law, "relations": relations}
