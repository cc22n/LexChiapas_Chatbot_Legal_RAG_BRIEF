from app.rag.agent_tools import get_article, get_article_ambiguity, query_graph

# BUG REAL (hallazgo #9, revision de seguridad 2026-08-04): get_article y
# query_graph tienen logica de desambiguacion real y cuidadosamente razonada
# (ver sus docstrings) para el caso en que fuzzy_ilike_pattern matchea mas
# de un documento activo (ej. los 4 libros del Codigo Civil) -- pero nunca
# tuvieron NINGUN test automatizado, solo verificacion manual contra la DB
# real (ver PLAN.md Fase 8 / LexChiapas_Plan_Futuro.md Parte 1.D). Estos
# tests cubren esa logica con un stub minimo de Session que devuelve filas
# predefinidas -- el SQL en si ya se verifico contra la DB real por separado,
# lo que se prueba aca es que hacer el codigo CON esas filas.


class _FakeRow:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def scalar_one(self):
        return self._rows[0]


class _FakeDB:
    """Devuelve un _FakeResult por cada llamada a execute(), en el orden en
    que se encolaron -- no interpreta el SQL, solo simula la secuencia de
    resultados que la funcion real bajo prueba espera recibir."""

    def __init__(self, results: list):
        self._queue = list(results)
        self.calls: list[dict] = []

    def execute(self, _stmt, params=None):
        self.calls.append(params or {})
        return self._queue.pop(0)


# ---------------------------------------------------------------------------
# get_article
# ---------------------------------------------------------------------------


def test_get_article_returns_none_when_no_rows():
    db = _FakeDB([_FakeResult([])])
    assert get_article(db, "ley que no existe", "5") is None


def test_get_article_single_document_no_ambiguity():
    rows = [_FakeRow(id=10, nombre="Ley de Aguas para el Estado de Chiapas", articulo_numero="5", content="texto del articulo 5")]
    db = _FakeDB([_FakeResult(rows)])
    chunk = get_article(db, "ley de aguas", "5")
    assert chunk is not None
    assert chunk.chunk_id == 10
    assert chunk.document_nombre == "Ley de Aguas para el Estado de Chiapas"
    assert chunk.similarity == 1.0
    assert chunk.passed_threshold is False  # gate propio, nunca el de similitud semantica


def test_get_article_ambiguous_match_resolved_by_exact_name():
    # Caso real documentado: "codigo civil" matchea los 4 libros -- si el
    # numero de articulo pedido coincide en mas de un libro (no deberia con
    # los datos reales, pero la logica debe manejarlo) Y el nombre exacto de
    # uno de los candidatos matchea `law_name`, se prefiere ESE.
    rows = [
        _FakeRow(id=1, nombre="Codigo Civil para el Estado de Chiapas - Libro Primero (De las Personas)", articulo_numero="5", content="libro 1"),
        _FakeRow(id=2, nombre="Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)", articulo_numero="5", content="libro 2"),
    ]
    db = _FakeDB([_FakeResult(rows)])
    chunk = get_article(db, "Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)", "5")
    assert chunk is not None
    assert chunk.chunk_id == 2
    assert chunk.content == "libro 2"


def test_get_article_ambiguous_match_without_exact_name_refuses_to_guess():
    # Sin match exacto de nombre entre los candidatos, la funcion NUNCA debe
    # adivinar cual de los documentos es el correcto (ver docstring: "el peor
    # error posible para una cita legal" seria citar la ley equivocada) --
    # debe devolver None, no el primero de la lista.
    rows = [
        _FakeRow(id=1, nombre="Codigo Civil para el Estado de Chiapas - Libro Primero (De las Personas)", articulo_numero="5", content="libro 1"),
        _FakeRow(id=2, nombre="Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)", articulo_numero="5", content="libro 2"),
    ]
    db = _FakeDB([_FakeResult(rows)])
    assert get_article(db, "codigo civil", "5") is None


# ---------------------------------------------------------------------------
# get_article_ambiguity (Fase 9.3 -- companero de get_article para saber POR
# QUE devolvio None cuando la razon es ambiguedad real, no ausencia)
# ---------------------------------------------------------------------------


def test_get_article_ambiguity_empty_when_no_candidates():
    db = _FakeDB([_FakeResult([])])
    assert get_article_ambiguity(db, "ley que no existe", "5") == []


def test_get_article_ambiguity_empty_when_single_candidate():
    rows = [_FakeRow(nombre="Ley de Aguas para el Estado de Chiapas")]
    db = _FakeDB([_FakeResult(rows)])
    assert get_article_ambiguity(db, "ley de aguas", "5") == []


def test_get_article_ambiguity_empty_when_exact_name_resolves_it():
    # Mismo caso que test_get_article_ambiguous_match_resolved_by_exact_name:
    # el nombre exacto ya resuelve cual usar dentro de get_article, asi que
    # NO es el caso "ambiguedad real" que amerita pedir aclaracion.
    rows = [
        _FakeRow(nombre="Codigo Civil para el Estado de Chiapas - Libro Primero (De las Personas)"),
        _FakeRow(nombre="Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)"),
    ]
    db = _FakeDB([_FakeResult(rows)])
    result = get_article_ambiguity(
        db, "Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)", "5"
    )
    assert result == []


def test_get_article_ambiguity_returns_candidates_when_genuinely_ambiguous():
    rows = [
        _FakeRow(nombre="Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)"),
        _FakeRow(nombre="Codigo Civil para el Estado de Chiapas - Libro Primero (De las Personas)"),
    ]
    db = _FakeDB([_FakeResult(rows)])
    result = get_article_ambiguity(db, "codigo civil", "5")
    assert result == [
        "Codigo Civil para el Estado de Chiapas - Libro Primero (De las Personas)",
        "Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)",
    ]


# ---------------------------------------------------------------------------
# query_graph -- desambiguacion cuando `articulo` esta presente
# ---------------------------------------------------------------------------


def test_query_graph_no_matching_document_returns_empty():
    db = _FakeDB([_FakeResult([])])
    assert query_graph(db, "ley que no existe", articulo="10") == []


def test_query_graph_single_document_match_no_ambiguity():
    matched = [_FakeRow(id=5, nombre="Ley de Aguas para el Estado de Chiapas")]
    relation_row = _FakeRow(
        relation_type="deroga", from_document_id=5, from_document_nombre="Ley de Aguas para el Estado de Chiapas",
        from_articulo="10", from_chunk_id=99, to_document_id=None, to_law_name_raw="Ley X",
        fecha=None, source_text="(DEROGADO)", extraction_method="regex",
    )
    db = _FakeDB([_FakeResult(matched), _FakeResult([1]), _FakeResult([relation_row])])
    result = query_graph(db, "ley de aguas", articulo="10")
    assert len(result) == 1
    assert result[0]["from_document_id"] == 5


def test_query_graph_ambiguous_match_with_articulo_narrows_to_exact_document():
    # Mismo caso real que get_article: varios documentos matchean por
    # substring, pero solo uno tiene el nombre EXACTO -- debe acotar la
    # consulta de relaciones a ese documento (narrowed_doc_id), no mezclar
    # from_articulo de los otros libros.
    matched = [
        _FakeRow(id=1, nombre="Codigo Civil para el Estado de Chiapas - Libro Primero (De las Personas)"),
        _FakeRow(id=2, nombre="Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)"),
    ]
    relation_row = _FakeRow(
        relation_type="reforma", from_document_id=2, from_document_nombre="Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)",
        from_articulo="93", from_chunk_id=77, to_document_id=2, to_law_name_raw="Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)",
        fecha=None, source_text="(REFORMADO)", extraction_method="regex",
    )
    db = _FakeDB([_FakeResult(matched), _FakeResult([1]), _FakeResult([relation_row])])
    result = query_graph(
        db, "Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)", articulo="93"
    )
    assert len(result) == 1
    # La query de relaciones (3ra llamada a execute) debe haberse acotado
    # por doc_id, no por el patron amplio -- confirma que narrowed_doc_id
    # SI se uso para filtrar en vez del ILIKE amplio sobre los 2 candidatos.
    assert db.calls[2].get("doc_id") == 2
    assert "pattern" not in db.calls[2]


def test_query_graph_ambiguous_match_without_exact_name_keeps_broad_filter():
    # Sin nombre exacto entre los candidatos, no hay forma segura de acotar
    # -- se mantiene el filtro amplio (documentado como riesgo conocido,
    # registrado via logger.warning, no silencioso) en vez de fallar o
    # adivinar cual de los documentos es el correcto.
    matched = [
        _FakeRow(id=1, nombre="Codigo Civil para el Estado de Chiapas - Libro Primero (De las Personas)"),
        _FakeRow(id=2, nombre="Codigo Civil para el Estado de Chiapas - Libro Segundo (De los Bienes)"),
    ]
    db = _FakeDB([_FakeResult(matched), _FakeResult([0]), _FakeResult([])])
    result = query_graph(db, "codigo civil", articulo="93")
    assert result == []
    # La query de relaciones debe haber usado el patron amplio (pattern),
    # no un doc_id puntual -- confirma que NO se acoto sin match exacto.
    assert "pattern" in db.calls[2]
    assert "doc_id" not in db.calls[2]
