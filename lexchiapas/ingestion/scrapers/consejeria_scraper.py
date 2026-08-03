import requests
from bs4 import BeautifulSoup

# BASE_URL original ("https://consejeriajuridica.chiapas.gob.mx/MarcoJuridico")
# NO funciona: ese dominio/ruta redirige a una pagina de un ayuntamiento
# municipal (Acala) que no tiene nada que ver con el marco juridico estatal.
# Verificado contra el sitio real: el listado de leyes vive en el dominio
# "institutodelaconsejeriajuridica.chiapas.gob.mx" (distinto del dominio
# "consejeriajuridica.chiapas.gob.mx" usado en los href de los PDFs dentro de
# esa misma pagina, ver nota en download_pdf).
BASE_URL = "https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/Leyes/"

# Dominio real donde SI responden los archivos PDF (los href en el HTML
# apuntan al dominio viejo "consejeriajuridica.chiapas.gob.mx", que da 404
# para el mismo path). Se usa como fallback en download_pdf.
_WORKING_PDF_HOST = "https://institutodelaconsejeriajuridica.chiapas.gob.mx"
_STALE_PDF_HOST = "https://consejeriajuridica.chiapas.gob.mx"


def list_available_laws() -> list[dict]:
    """Devuelve [{nombre, source_url}] de leyes/decretos/reglamentos listados.

    El selector `a[href$='.pdf']` SI matchea (confirmado contra el HTML real:
    140 links en la tabla de leyes). Pero el nombre de la ley NO esta en el
    texto del propio link: cada link es solo un icono (`<img>` sin alt), asi
    que `link.get_text(strip=True)` siempre da vacio. El nombre real vive en
    la celda `<td>` anterior dentro de la misma fila `<tr id="fila_tabla">`,
    por eso se recorre por fila en vez de por link suelto.
    """
    response = requests.get(BASE_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    laws = []
    for row in soup.select("tr#fila_tabla"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        nombre = cells[1].get_text(strip=True)
        link = cells[2].find("a", href=True)
        if not link:
            continue
        href = link["href"]
        if nombre and href.lower().endswith(".pdf"):
            laws.append({"nombre": nombre, "source_url": href})
    return laws


def download_pdf(url: str) -> bytes:
    """Descarga el PDF de una ley.

    Los href del listado real apuntan al dominio viejo
    ("consejeriajuridica.chiapas.gob.mx"), que devuelve 404 para el mismo
    path (confirmado contra varios archivos reales). El dominio que si sirve
    el archivo es "institutodelaconsejeriajuridica.chiapas.gob.mx". Se
    intenta primero la URL tal cual (por si el sitio se arregla en el
    futuro) y si falla con 404 se reintenta con el dominio que si funciona.
    """
    response = requests.get(url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    if response.status_code == 404 and url.startswith(_STALE_PDF_HOST):
        fallback_url = url.replace(_STALE_PDF_HOST, _WORKING_PDF_HOST, 1)
        response = requests.get(fallback_url, timeout=60, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    return response.content
