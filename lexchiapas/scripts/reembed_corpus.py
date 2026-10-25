"""Re-embebe los chunks con el modelo de ai_config.json embeddings.model.

Uso (desde lexchiapas/, con ai_config.json YA apuntando al modelo destino):
    python -m scripts.reembed_corpus --dry-run          # cuenta pendientes y muestra textos
    python -m scripts.reembed_corpus --limit 64         # prueba chica
    python -m scripts.reembed_corpus                    # corrida completa

Reanudable: solo toca filas con embedding_model distinto del destino, asi que
una corrida interrumpida se continua volviendo a ejecutar el mismo comando.
Mientras haya filas del modelo anterior, dense_search las ignora (filtra por
embedding_model), asi que nunca se comparan vectores de modelos distintos.

El texto a embeber se reconstruye desde la DB con LegalChunk.to_embedding_text
(ley, titulo, capitulo, articulo + contenido), el mismo formato que usa la
ingesta, para que chunks viejos y nuevos queden consistentes.

Rollback: antes de migrar, guardar una copia (por ejemplo CREATE TABLE
chunks_embedding_backup_AAAAMMDD AS SELECT id, embedding, embedding_model FROM
chunks), y para deshacer devolver esos vectores y revertir ai_config.json.
Los umbrales de similitud (retrieval, Capa 1, cache) dependen del modelo:
despues de migrar hay que recalibrarlos con el golden dataset.
"""

import argparse
import time

from sqlalchemy import text

from app.config import get_ai_config
from app.database import SessionLocal
from app.llm.providers import embed_texts
from app.rag.chunker import LegalChunk
from app.rag.retriever import to_vector_literal


def build_embedding_text(row) -> str:
    return LegalChunk(
        articulo_numero=row.articulo_numero,
        titulo=row.titulo,
        capitulo=row.capitulo,
        seccion=row.seccion,
        content=row.content,
        document_nombre=row.nombre,
    ).to_embedding_text()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--batch", type=int, default=64, help="textos por request (default 64)")
    parser.add_argument("--limit", type=int, default=None, help="procesar solo N chunks (prueba)")
    parser.add_argument("--include-inactive", action="store_true", help="tambien documentos inactivos")
    parser.add_argument("--dry-run", action="store_true", help="no llama a la API ni escribe")
    args = parser.parse_args()

    cfg = get_ai_config()["embeddings"]
    target, dimension = cfg["model"], cfg["dimension"]
    provider = cfg.get("provider", "nvidia_nim")

    db = SessionLocal()
    active_clause = "" if args.include_inactive else "AND d.is_active"
    ids = db.execute(
        text(
            f"""
            SELECT c.id FROM chunks c JOIN documents d ON d.id = c.document_id
            WHERE c.embedding_model <> :target {active_clause}
            ORDER BY c.id
            """
        ),
        {"target": target},
    ).scalars().all()
    if args.limit:
        ids = ids[: args.limit]
    print(f"destino: {provider}/{target} dim={dimension} | chunks pendientes: {len(ids)}", flush=True)

    select_sql = text(
        """
        SELECT c.id, d.nombre, c.titulo, c.capitulo, c.seccion, c.articulo_numero, c.content
        FROM chunks c JOIN documents d ON d.id = c.document_id
        WHERE c.id = ANY(:ids) ORDER BY c.id
        """
    )
    if args.dry_run:
        for row in db.execute(select_sql, {"ids": ids[:2]}).all():
            print("muestra:", build_embedding_text(row)[:200].replace("\n", " "), flush=True)
        return

    t0, done = time.time(), 0
    for start in range(0, len(ids), args.batch):
        rows = db.execute(select_sql, {"ids": ids[start : start + args.batch]}).all()
        vectors = embed_texts([build_embedding_text(r) for r in rows], input_type="passage")
        if len(vectors) != len(rows) or any(len(v) != dimension for v in vectors):
            raise RuntimeError(
                f"respuesta inesperada: {len(vectors)} vectores para {len(rows)} textos, "
                f"dimensiones {sorted({len(v) for v in vectors})} (esperado {dimension})"
            )
        db.execute(
            text("UPDATE chunks SET embedding = CAST(:e AS vector), embedding_model = :m WHERE id = :id"),
            [{"e": to_vector_literal(v), "m": target, "id": r.id} for r, v in zip(rows, vectors)],
        )
        db.commit()
        done += len(rows)
        print(f"  {done}/{len(ids)} ({time.time() - t0:.0f}s)", flush=True)

    # Entradas del cache semantico del modelo anterior: lookup() ya las ignora
    # (exige embedding_model = actual); se limpian solo por higiene.
    removed = db.execute(text("DELETE FROM semantic_cache WHERE embedding_model <> :t"), {"t": target}).rowcount
    db.commit()
    left = db.execute(text("SELECT count(*) FROM chunks c JOIN documents d ON d.id=c.document_id WHERE c.embedding_model <> :t AND d.is_active"), {"t": target}).scalar()
    print(f"listo: {done} chunks re-embebidos en {time.time() - t0:.0f}s | cache semantico limpiado: {removed} | activos aun con modelo anterior: {left}", flush=True)
    db.close()


if __name__ == "__main__":
    main()
