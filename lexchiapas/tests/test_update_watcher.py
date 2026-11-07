"""Vigilante de leyes (app.workers.update_watcher): solo detecta y avisa."""

import json

from app.workers import update_watcher
from app.workers.update_watcher import build_alert, detect_updates

CONGRESO = "https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/"


def _doc(i, nombre, url):
    return {"id": i, "nombre": nombre, "source_url": url}


def _law(nombre, url):
    return {"nombre": nombre, "source_url": url}


def test_unchanged_url_is_not_reported():
    docs = [_doc(1, "Ley de Archivos del Estado de Chiapas", CONGRESO + "LEY_0001.pdf?v=NQ==")]
    cat = {"congreso": [_law("LEY DE ARCHIVOS DEL ESTADO DE CHIAPAS", CONGRESO + "LEY_0001.pdf?v=NQ==")]}
    report = detect_updates(docs, cat)
    assert report["changed"] == [] and report["unmatched"] == [] and report["new_laws"] == []


def test_changed_version_param_is_reported():
    docs = [_doc(2, "Codigo Penal para el Estado de Chiapas", CONGRESO + "LEY_0012.pdf?v=NDM=")]
    cat = {"congreso": [_law("CÓDIGO PENAL PARA EL ESTADO DE CHIAPAS", CONGRESO + "LEY_0012.pdf?v=NDU=")]}
    report = detect_updates(docs, cat)
    assert [c["document_id"] for c in report["changed"]] == [2]
    assert report["changed"][0]["new_url"].endswith("v=NDU=")


def test_double_space_in_catalog_name_still_matches():
    # Caso real: 'LEY DE  VICTIMAS' (dos espacios) en el catalogo del Congreso.
    docs = [_doc(3, "Ley de Victimas para el Estado de Chiapas", CONGRESO + "LEY_0080.pdf?v=Ng==")]
    cat = {"congreso": [_law("LEY DE  VÍCTIMAS PARA EL ESTADO DE CHIAPAS", CONGRESO + "LEY_0080.pdf?v=Ng==")]}
    report = detect_updates(docs, cat)
    assert report["unmatched"] == [] and report["changed"] == [] and report["new_laws"] == []


def test_ambiguous_and_missing_matches_are_unmatched_not_changed():
    docs = [
        _doc(4, "Ley de Aguas", CONGRESO + "LEY_0002.pdf?v=1"),
        _doc(5, "Ley Inexistente", CONGRESO + "LEY_0003.pdf?v=1"),
    ]
    cat = {"congreso": [_law("LEY DE AGUAS PARA EL ESTADO", CONGRESO + "A.pdf?v=2"),
                        _law("LEY DE AGUAS RESIDUALES", CONGRESO + "B.pdf?v=2")]}
    report = detect_updates(docs, cat)
    assert report["changed"] == []
    reasons = {u["nombre"]: u["reason"] for u in report["unmatched"]}
    assert reasons == {"Ley de Aguas": "ambiguo", "Ley Inexistente": "sin_match"}


def test_new_laws_only_from_congreso_deduped_and_without_abrogated():
    docs = [_doc(6, "Ley de Archivos del Estado de Chiapas", CONGRESO + "LEY_0001.pdf?v=1")]
    cat = {
        "congreso": [
            _law("LEY DE ARCHIVOS DEL ESTADO DE CHIAPAS", CONGRESO + "LEY_0001.pdf?v=1"),
            _law("LEY NUEVA DE PRUEBA", CONGRESO + "LEY_0200.pdf?v=1"),
            _law("LEY  NUEVA DE PRUEBA", CONGRESO + "LEY_0200.pdf?v=1"),  # duplicado con doble espacio
            _law("LEY ABROGADA MEDIANTE DECRETO 018. LEY VIEJA", CONGRESO + "LEY_0201.pdf?v=1"),
            _law("DECLARATORIA DE INICIO DE VIGENCIA DEL CODIGO X", CONGRESO + "LEY_0202.pdf?v=1"),
        ],
        "consejeria": [_law("LEY SOLO EN CONSEJERIA", "https://consejeriajuridica.chiapas.gob.mx/x.pdf")],
    }
    report = detect_updates(docs, cat)
    assert [n["nombre"] for n in report["new_laws"]] == ["LEY NUEVA DE PRUEBA"]


def test_document_with_unknown_source_is_listed_not_compared():
    docs = [_doc(7, "Ley Externa", "https://ejemplo.org/ley.pdf"), _doc(8, "Sin URL", None)]
    report = detect_updates(docs, {"congreso": []})
    assert report["unknown_source"] == ["Ley Externa", "Sin URL"]
    assert report["changed"] == []


def test_build_alert_none_when_nothing_to_report():
    empty = {"changed": [], "unmatched": [], "unknown_source": [], "new_laws": []}
    assert build_alert(empty, None) is None
    assert build_alert(empty, []) is None


def test_build_alert_mentions_changes_new_laws_and_does_not_claim_updates():
    report = {"changed": [{"nombre": "Codigo Penal"}], "unmatched": [], "unknown_source": [], "new_laws": []}
    text = build_alert(report, [f"LEY {i}" for i in range(12)])
    assert "Codigo Penal" in text and "12 ley(es) nueva(s)" in text and "(y 4 mas)" in text
    assert "No se actualizo nada" in text


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value):
        self.store[key] = value


def _patch_task(monkeypatch, docs, congreso_laws):
    fake = _FakeRedis()
    sent = []
    monkeypatch.setattr(update_watcher, "_load_documents", lambda: docs)
    monkeypatch.setattr(update_watcher, "_get_redis_client", lambda: fake)
    monkeypatch.setattr(update_watcher, "send_admin_telegram_alert", lambda text: sent.append(text) or True)
    monkeypatch.setattr(update_watcher.congreso_scraper, "list_available_laws", lambda: congreso_laws)
    return fake, sent


def test_task_first_run_sets_baseline_second_run_alerts_new_law(monkeypatch):
    docs = [_doc(1, "Ley de Archivos del Estado de Chiapas", CONGRESO + "LEY_0001.pdf?v=1")]
    laws = [_law("LEY DE ARCHIVOS DEL ESTADO DE CHIAPAS", CONGRESO + "LEY_0001.pdf?v=1")]
    fake, sent = _patch_task(monkeypatch, docs, laws)

    first = update_watcher.law_update_watcher()
    assert first["new_since_last"] is None and first["alerted"] is False and sent == []
    assert json.loads(fake.store["law_watcher:catalog_names"]) == ["LEY DE ARCHIVOS DEL ESTADO DE CHIAPAS"]

    laws.append(_law("LEY NUEVA DE PRUEBA", CONGRESO + "LEY_0200.pdf?v=1"))
    second = update_watcher.law_update_watcher()
    assert second["new_since_last"] == ["LEY NUEVA DE PRUEBA"] and second["alerted"] is True
    assert "LEY NUEVA DE PRUEBA" in sent[0]


def test_task_alerts_changed_url_and_never_reingests(monkeypatch):
    docs = [_doc(2, "Codigo Penal para el Estado de Chiapas", CONGRESO + "LEY_0012.pdf?v=NDM=")]
    laws = [_law("CODIGO PENAL PARA EL ESTADO DE CHIAPAS", CONGRESO + "LEY_0012.pdf?v=NDU=")]
    fake, sent = _patch_task(monkeypatch, docs, laws)
    # Si el vigilante descargara algo, estas funciones explotarian.
    monkeypatch.setattr(update_watcher.congreso_scraper, "download_pdf", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("no debe descargar")), raising=False)

    result = update_watcher.law_update_watcher()
    assert result["changed"] == ["Codigo Penal para el Estado de Chiapas"]
    assert result["alerted"] is True and "No se actualizo nada" in sent[0]


def test_task_survives_a_failing_source(monkeypatch):
    docs = [_doc(3, "Ley de Archivos del Estado de Chiapas", CONGRESO + "LEY_0001.pdf?v=1")]
    fake, sent = _patch_task(monkeypatch, docs, [])

    def boom():
        raise RuntimeError("sin red")

    monkeypatch.setattr(update_watcher.congreso_scraper, "list_available_laws", boom)
    result = update_watcher.law_update_watcher()
    assert result["errors"] and result["alerted"] is False
    assert "law_watcher:catalog_names" not in fake.store  # no pisa la linea base con un catalogo vacio
