import app.rag.reranker as reranker
from app.rag.retriever import RetrievedChunk


def _chunk(i: int, passed: bool = True) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=i, document_nombre="Ley X", articulo_numero=str(i), content=f"texto {i}",
        similarity=0.7, passed_threshold=passed,
    )


def _setup(monkeypatch, scores, fusion, top_k=3):
    retrieval = {"top_k": top_k}
    if fusion is not None:
        retrieval["rerank_fusion"] = fusion
    monkeypatch.setattr(reranker, "get_ai_config", lambda: {"retrieval": retrieval})
    monkeypatch.setattr(reranker, "get_relevance_scores", lambda q, passages: (scores, "nvidia_nim"))


def test_without_fusion_the_reranker_score_alone_orders_within_threshold_group(monkeypatch):
    # el candidato 1 (primero en hybrid_search) tiene el peor puntaje del reranker
    candidates = [_chunk(1), _chunk(2), _chunk(3), _chunk(4)]
    _setup(monkeypatch, [0.1, 0.9, 0.8, 0.7], fusion=None)
    assert [c.chunk_id for c in reranker.rerank("q", candidates)] == [2, 3, 4]


def test_rrf_keeps_a_chunk_strong_in_hybrid_but_buried_by_the_reranker(monkeypatch):
    # Caso real E1 (adopcion): hybrid_search lo tenia en el rank 2 y el reranker
    # en el 16. Con RRF debe entrar al top-K en vez de quedar fuera.
    # El candidato 2 es el ultimo para el reranker (rank 6) pero el 2.o en hybrid_search.
    # RRF: c3 .03227, c1 .03178, c4 .03175, c2 .03128 (4.o), c5 .03126, c6 .03078.
    candidates = [_chunk(i) for i in range(1, 7)]
    scores = [0.5, 0.1, 0.9, 0.8, 0.7, 0.6]
    _setup(monkeypatch, scores, fusion="rrf", top_k=4)
    assert 2 in [c.chunk_id for c in reranker.rerank("q", candidates)]
    _setup(monkeypatch, scores, fusion=None, top_k=4)
    assert 2 not in [c.chunk_id for c in reranker.rerank("q", candidates)]  # el orden anterior lo perdia


def test_passed_threshold_is_still_the_first_criterion_with_rrf(monkeypatch):
    # Invariante "threshold primero": un chunk que NO paso el umbral nunca
    # queda por encima de uno que si, aunque sea el mejor en ambos rankings.
    candidates = [_chunk(1, passed=False), _chunk(2), _chunk(3), _chunk(4)]
    _setup(monkeypatch, [0.99, 0.5, 0.4, 0.3], fusion="rrf", top_k=4)
    order = [c.chunk_id for c in reranker.rerank("q", candidates)]
    assert order[-1] == 1 and set(order[:3]) == {2, 3, 4}


def test_rrf_scores_combine_both_rankings():
    # candidato 0: hybrid 1, reranker 3 | candidato 1: hybrid 2, reranker 1 | candidato 2: hybrid 3, reranker 2
    scores = reranker._rrf_scores([0.1, 0.9, 0.5])
    expected = [1 / 61 + 1 / 63, 1 / 62 + 1 / 61, 1 / 63 + 1 / 62]
    assert all(abs(a - b) < 1e-12 for a, b in zip(scores, expected))
