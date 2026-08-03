import re

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://web.congresochiapas.gob.mx/trabajo-legislativo/legislacion-vigente"

_ONCLICK_URL_RE = re.compile(r"goToUrl\('([^']+)'\)")


def list_available_laws() -> list[dict]:
    """Devuelve [{nombre, source_url}] de la legislacion vigente listada.

    NOTA (corregida, previamente esta funcion asumia que hacia falta un
    navegador headless -- eso resulto ser INCORRECTO tras verificar de
    nuevo contra el sitio real):

    El listado SI esta en el HTML estatico que devuelve `requests.get()`,
    no se carga por JavaScript/AJAX. El selector viejo `a[href$='.pdf']`
    daba 0 resultados porque el link al PDF no vive en un `<a href=...>`:
    cada fila de la tabla es un `<tr onclick="goToUrl('URL_DEL_PDF')">`, y
    el `<a>` dentro de la celda de descarga es solo un icono sin `href`
    (el link real esta en el atributo `onclick` de la fila, no en un
    `href`). El nombre de la ley esta en la segunda celda `<td>` de esa
    misma fila (la primera celda es solo un numero consecutivo). Tambien
    hay filas de encabezado de seccion sin `onclick` (p.ej.
    `<tr><th colspan="8">CODIGOS</th></tr>`) que se excluyen solas al
    filtrar por `tr[onclick]`.

    Confirmado contra el sitio real: 146 filas con `onclick` conteniendo
    una URL de PDF (dominio `congresochiapas.gob.mx/new/Info-Parlamentaria/`).
    """
    response = requests.get(BASE_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    laws = []
    for row in soup.select("tr[onclick]"):
        onclick = row.get("onclick", "")
        match = _ONCLICK_URL_RE.search(onclick)
        if not match:
            continue
        href = match.group(1)

        cells = row.find_all("td")
        if len(cells) < 2:
            continue
        nombre = cells[1].get_text(strip=True)

        is_pdf = href.lower().endswith(".pdf") or ".pdf?" in href.lower()
        if nombre and is_pdf:
            laws.append({"nombre": nombre, "source_url": href})
    return laws


def download_pdf(url: str) -> bytes:
    response = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return response.content
