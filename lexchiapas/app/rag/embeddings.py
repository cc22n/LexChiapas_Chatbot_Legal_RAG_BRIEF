import re

from sqlalchemy.orm import Session

from app.config import get_ai_config
from app.llm.providers import embed_text
from app.models import Chunk, Document
from app.rag.chunker import LegalChunk

# Presupuesto conservador de caracteres para no exceder el limite de tokens
# del modelo de embeddings. Bug real encontrado cargando la Ley de
# Bibliotecas para el Estado de Chiapas: su Articulo 15 tiene 4157
# caracteres de contenido y la API de NVIDIA (nvidia/nv-embedqa-e5-v5)
# rechazo la llamada con 400 "Input length 704 exceeds maximum allowed token
# size 512". La unidad de chunk natural sigue siendo el articulo (ver
# app.rag.chunker.chunk_legal_text), pero un articulo real puede exceder ese
# limite; en vez de fallar toda la ingesta de la ley por un solo articulo
# largo, se sub-divide en piezas mas chicas que comparten el mismo
# articulo_numero/titulo/capitulo/seccion (misma cita), en vez de un corte
# ciego por caracteres. Un primer intento con 1500 caracteres SIGUIO
# fallando (400 "Input length 576 exceeds maximum allowed token size 512"):
# la relacion real caracter/token de este texto legal en espanol resulto mas
# cercana a 2.6 que a los 3-4 caracteres por token asumidos inicialmente. Se
# bajo a 900 caracteres, que deja margen incluso para el encabezado
# estructural que to_embedding_text antepone a cada pieza.
MAX_EMBEDDING_CHARS = 900


def _split_content_for_embedding(content: str, max_chars: int = MAX_EMBEDDING_CHARS) -> list[str]:
    """Parte content en piezas <= max_chars respetando limites de linea y,
    si una sola linea excede el limite, de oracion. La mayoria de los
    articulos NO se dividen (devuelve una sola pieza) porque estan por
    debajo de max_chars; esto solo entra en juego para articulos reales
    inusualmente largos.
    """
    if len(content) <= max_chars:
        return [content]

    pieces: list[str] = []
    current = ""
    for line in content.splitlines():
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) <= max_chars:
            current = candidate
            continue

        if current:
            pieces.append(current)

        if len(line) <= max_chars:
            current = line
            continue

        # Una sola linea real mas larga que max_chars (raro): partir por
        # oracion en vez de cortar a mitad de palabra.
        current = ""
        for sentence in re.split(r"(?<=[.;:])\s+", line):
            sentence_candidate = f"{current} {sentence}" if current else sentence
            if len(sentence_candidate) <= max_chars:
                current = sentence_candidate
            else:
                if current:
                    pieces.append(current)
                current = sentence

    if current:
        pieces.append(current)
    return pieces


def embed_and_store_chunks(db: Session, document: Document, legal_chunks: list[LegalChunk]) -> int:
    """Genera embeddings para cada LegalChunk y los guarda en la tabla chunks.

    Devuelve el numero de chunks creados (para ingestion_logs.chunks_created).
    """
    current_model = get_ai_config()["embeddings"]["model"]
    created = 0
    for legal_chunk in legal_chunks:
        pieces = _split_content_for_embedding(legal_chunk.content)
        multipart = len(pieces) > 1

        for i, piece in enumerate(pieces, start=1):
            embedding = embed_text(
                legal_chunk.to_embedding_text(piece), input_type="passage"
            )
            chunk = Chunk(
                document_id=document.id,
                articulo_numero=legal_chunk.articulo_numero,
                titulo=legal_chunk.titulo,
                capitulo=legal_chunk.capitulo,
                seccion=legal_chunk.seccion,
                content=piece,
                chunk_metadata={
                    "titulo": legal_chunk.titulo,
                    "capitulo": legal_chunk.capitulo,
                    "seccion": legal_chunk.seccion,
                    "parte": i if multipart else None,
                    "partes_totales": len(pieces) if multipart else None,
                },
                embedding=embedding,
                embedding_model=current_model,
            )
            db.add(chunk)
            created += 1

    db.commit()
    return created
