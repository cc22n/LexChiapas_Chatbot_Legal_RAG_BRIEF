from app.rag import generator
from app.rag.generator import DISCLAIMER, NO_ENCONTRADO
from app.schemas.chat import RetrievedChunk


def test_generate_answer_survives_null_content_from_moderation(monkeypatch):
    # Un proveedor que bloquea por moderacion devuelve content=None; antes
    # eso lanzaba TypeError (None + DISCLAIMER).
    monkeypatch.setattr(
        generator, "generate_with_fallback", lambda messages: (None, "modelo-x", 10, 0)
    )
    chunk = RetrievedChunk(
        chunk_id=1,
        document_nombre="Codigo Penal",
        articulo_numero="1",
        content="texto",
        similarity=0.9,
        passed_threshold=True,
    )

    answer, model, _, _ = generator.generate_answer("pregunta", [chunk])

    assert answer == NO_ENCONTRADO + DISCLAIMER
    assert model == "modelo-x"
