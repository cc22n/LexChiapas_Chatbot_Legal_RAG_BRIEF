from urllib.parse import quote, unquote, urlsplit, urlunsplit

from app.database import SessionLocal
from app.models import Document
from app.rag.text_utils import strip_accents
from app.workers.celery_app import celery_app
from app.workers.ingestion_tasks import ingest_document
from ingestion.parsers.pdf_parser import extract_text_from_pdf
from ingestion.scrapers import congreso_scraper, consejeria_scraper
from ingestion.scrapers.consejeria_scraper import _STALE_PDF_HOST, _WORKING_PDF_HOST

# Dominios usados para saber de que scraper vino un Document.source_url ya
# guardado. Critico: NUNCA comparar un documento cargado de una fuente
# contra el listado de la OTRA fuente -- los dominios son distintos por
# diseno, asi que esa comparacion siempre marcaria "URL distinta" como falso
# positivo aunque la ley no haya cambiado en absoluto.
_CONGRESO_HOST_MARKER = "congresochiapas.gob.mx"
# Cubre tanto el host viejo (consejeriajuridica.chiapas.gob.mx, usado en los
# href originales) como el nuevo que realmente sirve el listado/PDFs
# (institutodelaconsejeriajuridica.chiapas.gob.mx) -- ver notas en
# ingestion/scrapers/consejeria_scraper.py.
_CONSEJERIA_HOST_MARKER = "consejeriajuridica.chiapas.gob.mx"


def _normalize_url_for_comparison(url: str | None) -> str:
    """Normaliza un source_url de Consejeria antes de comparar por igualdad.

    Bug real encontrado y corregido en esta misma tarea (verificado contra
    el estado real de la DB, no solo en teoria): consejeria_scraper.
    list_available_laws() devuelve el href TAL CUAL esta en el HTML fuente
    -- dominio viejo (consejeriajuridica.chiapas.gob.mx) SIN url-encodear
    (espacios y acentos literales, ej. "LEY DE SALUD ... CHIAPAS.pdf"). Los
    Document.source_url ya guardados en la DB, en cambio, se guardaron con
    el dominio nuevo que si sirve el archivo
    (institutodelaconsejeriajuridica.chiapas.gob.mx) y url-encodeados (ej.
    "LEY%20DE%20SALUD%20...%20CHIAPAS.pdf", ver ingestion/scrapers/
    consejeria_scraper.py). Una comparacion de string cruda entre ambas
    formas SIEMPRE da "distinta" aunque la ley no haya cambiado en absoluto
    -- confirmado en vivo: sin esta normalizacion, los 9 documentos activos
    de Consejeria salian como "candidatos a reforma" en la primera corrida
    real de deteccion, un falso positivo generalizado que hubiera
    reingerido innecesariamente casi todo el corpus de Consejeria en la
    primera ejecucion de este Celery Beat. Se normaliza decodeando
    porcentaje y homologando el host antes de comparar (no se toca el valor
    real que se descarga ni el que se persiste, solo el usado para decidir
    si "cambio")."""
    if not url:
        return ""
    decoded = unquote(url)
    decoded = decoded.replace(_STALE_PDF_HOST, _WORKING_PDF_HOST)
    return decoded.strip().lower()


def _to_storable_url(url: str, source: str) -> str:
    """Forma canonica a persistir en Document.source_url tras una
    reingesta real. Para Congreso, el href ya viene listo para usarse tal
    cual (confirmado en Fase 3.7). Para Consejeria, se resuelve al host que
    realmente sirve el archivo y se url-encodea el path, siguiendo la misma
    convencion ya usada por todos los scripts load_*.py existentes (ej.
    "...LEY%20DE%20SALUD...pdf", no espacios/acentos literales) -- asi el
    valor guardado sirve para descargar directo sin depender del fallback
    de 404 de consejeria_scraper.download_pdf, y sigue comparando limpio en
    la proxima corrida de este mismo chequeo."""
    if source != "consejeria":
        return url
    resolved = url.replace(_STALE_PDF_HOST, _WORKING_PDF_HOST)
    parts = urlsplit(resolved)
    path = quote(unquote(parts.path))
    return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))


def _normalize_name(name: str) -> str:
    """Mismo patron de matching verificado en Fase 3.7 (scraper de Congreso,
    ver PLAN.md): quitar acentos y mayusculas, comparar por substring en
    cualquier direccion. NO usar igualdad estricta -- los nombres en las
    fuentes casi nunca coinciden caracter por caracter contra
    Document.nombre (mayusculas distintas, orden de palabras, etc.)."""
    return strip_accents(name).strip().upper()


def _guess_source(url: str | None) -> str | None:
    """Determina de que scraper vino un source_url ya guardado, por dominio.
    Devuelve None si el dominio no se reconoce (no hay forma segura de
    comparar, se debe saltar ese documento en vez de arriesgar)."""
    if not url:
        return None
    lowered = url.lower()
    if _CONGRESO_HOST_MARKER in lowered:
        return "congreso"
    if _CONSEJERIA_HOST_MARKER in lowered:
        return "consejeria"
    return None


def _find_match(document_nombre: str, laws: list[dict]) -> dict | None:
    """Busca la entrada del listado actual del scraper que corresponde a un
    Document ya cargado, por nombre normalizado (substring en cualquier
    direccion). Mismo patron verificado en Fase 3.7 contra los 17 documentos
    activos de la epoca (0 sin match, 0 ambiguos).

    Si mas de una ley del listado matchea el mismo nombre normalizado, el
    match se descarta por ambiguo -- mejor perder una actualizacion real que
    arriesgar reingerir el documento equivocado sobre otro (ver incidente
    real Codigo Fiscal / Codigo de la Hacienda Publica, mismo tipo de
    ambiguedad de nombre)."""
    normalized_doc = _normalize_name(document_nombre)
    matches = []
    for law in laws:
        normalized_law = _normalize_name(law.get("nombre", ""))
        if not normalized_law:
            continue
        if normalized_doc in normalized_law or normalized_law in normalized_doc:
            matches.append(law)
    if len(matches) == 1:
        return matches[0]
    return None


@celery_app.task(name="app.workers.update_tasks.check_for_law_updates")
def check_for_law_updates() -> dict:
    """Corre diario (Celery Beat, 3am) para detectar reformas de leyes ya
    cargadas y reingerirlas.

    Senal real usada para detectar cambio: Document.fecha_ultima_reforma
    existe como columna pero no se llena de forma confiable hoy (ver
    app/models/document.py), asi que no sirve como senal automatizada. En su
    lugar se compara el source_url guardado contra el que el scraper de la
    MISMA fuente (Congreso o Consejeria, nunca cruzado) devuelve HOY para
    esa misma ley por nombre normalizado. Si el nombre matchea de forma no
    ambigua y la URL cambio, es candidato real a reforma -- Congreso en
    particular usa un query param de version (?v=NN, base64 de un numero)
    que cambia cuando el documento se re-publica.

    Para cada candidato real: descarga el PDF nuevo, extrae texto, reemplaza
    los chunks del documento (ingest_document con replace_existing=True) y
    actualiza Document.source_url. Un fallo en un documento (descarga,
    parsing, embeddings) se registra en errors y NO detiene el chequeo del
    resto -- no se hace commit parcial de ese documento (rollback en el
    except) para no dejar Document.source_url apuntando a una URL cuyo
    contenido no se termino de reingerir con exito.
    """
    db = SessionLocal()
    checked = 0
    updated_documents: list[str] = []
    errors: list[dict] = []

    try:
        congreso_laws: list[dict] | None = None
        consejeria_laws: list[dict] | None = None

        documents = db.query(Document).filter(Document.is_active.is_(True)).all()

        for document in documents:
            checked += 1
            source = _guess_source(document.source_url)
            if source is None:
                # source_url ausente o de un dominio no reconocido: no hay
                # forma segura de saber contra que scraper comparar.
                continue

            if source == "congreso":
                if congreso_laws is None:
                    congreso_laws = congreso_scraper.list_available_laws()
                laws = congreso_laws
                scraper = congreso_scraper
            else:
                if consejeria_laws is None:
                    consejeria_laws = consejeria_scraper.list_available_laws()
                laws = consejeria_laws
                scraper = consejeria_scraper

            match = _find_match(document.nombre, laws)
            if match is None:
                continue

            new_url = match["source_url"]
            if _normalize_url_for_comparison(new_url) == _normalize_url_for_comparison(document.source_url):
                # Ver _normalize_url_for_comparison: sin esto, cada
                # documento de Consejeria saldria como "candidato" solo por
                # la diferencia de host/encoding entre el href crudo del
                # scraper y la URL ya resuelta que se guardo al cargarlo.
                continue

            storable_url = _to_storable_url(new_url, source)

            # Candidato real: mismo nombre (casi-exacto, normalizado), URL
            # distinta (mas alla de host/encoding) dentro de la misma
            # fuente de origen.
            try:
                pdf_bytes = scraper.download_pdf(new_url)
                raw_text = extract_text_from_pdf(pdf_bytes)
                if not raw_text.strip():
                    raise ValueError("el PDF nuevo se extrajo vacio, no se reingiere a ciegas")

                ingest_document(document.id, raw_text, replace_existing=True)

                document.source_url = storable_url
                db.commit()
                updated_documents.append(document.nombre)
            except Exception as exc:
                db.rollback()
                errors.append({"document": document.nombre, "error": str(exc)})

        return {
            "checked": checked,
            "updated": len(updated_documents),
            "updated_documents": updated_documents,
            "errors": errors,
        }
    finally:
        db.close()
