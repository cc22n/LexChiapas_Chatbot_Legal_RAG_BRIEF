from types import SimpleNamespace

import app.llm.providers as providers
import app.rag.retriever as retriever


class _RecordingEmbeddings:
    def __init__(self, indices):
        self.calls = []
        self._indices = indices

    def create(self, **kwargs):
        self.calls.append(kwargs)
        # devuelve los items en el orden indicado para comprobar que se reordenan por index
        return SimpleNamespace(
            data=[SimpleNamespace(index=i, embedding=[float(i)] * 3) for i in self._indices]
        )


def _use(monkeypatch, provider, indices=(0,)):
    rec = _RecordingEmbeddings(indices)
    monkeypatch.setattr(providers, "_get_embeddings_client", lambda: SimpleNamespace(embeddings=rec))
    monkeypatch.setattr(
        providers, "get_ai_config",
        lambda: {"embeddings": {"provider": provider, "model": "m-x", "dimension": 1024}},
    )
    return rec


def test_openai_style_sends_dimensions_as_parameter_without_input_type(monkeypatch):
    rec = _use(monkeypatch, "openai")
    providers.embed_text("hola", input_type="passage")
    call = rec.calls[0]
    assert call["dimensions"] == 1024
    assert "extra_body" not in call  # OpenAI no usa input_type (modelo simetrico)
    assert call["model"] == "m-x" and call["input"] == ["hola"]


def test_nvidia_style_keeps_input_type_and_dimensions_in_extra_body(monkeypatch):
    rec = _use(monkeypatch, "nvidia_nim")
    providers.embed_text("hola", input_type="query")
    call = rec.calls[0]
    assert call["extra_body"] == {"input_type": "query", "dimensions": 1024}
    assert "dimensions" not in call


def test_embed_texts_returns_vectors_in_input_order_even_if_api_reorders(monkeypatch):
    rec = _use(monkeypatch, "openai", indices=(2, 0, 1))
    vectors = providers.embed_texts(["a", "b", "c"], input_type="passage")
    assert [v[0] for v in vectors] == [0.0, 1.0, 2.0]
    assert rec.calls[0]["input"] == ["a", "b", "c"]


class _CapturingDb:
    def __init__(self):
        self.sql = None
        self.params = None

    def execute(self, statement, params):
        self.sql, self.params = str(statement), params
        return SimpleNamespace(all=lambda: [])


def test_dense_search_only_compares_vectors_of_the_current_embedding_model(monkeypatch):
    # ALT-07: sin este filtro, tras una migracion de modelo se comparaban
    # vectores de espacios distintos (coseno sin significado).
    monkeypatch.setattr(retriever, "get_ai_config", lambda: {"embeddings": {"model": "modelo-actual"}})
    db = _CapturingDb()
    retriever.dense_search(db, [0.1, 0.2], k=5, threshold=0.3)
    assert "c.embedding_model = :embedding_model" in db.sql
    assert db.params["embedding_model"] == "modelo-actual"
