from bs4 import BeautifulSoup


def extract_text_from_html(html: str) -> str:
    """Extrae el texto plano del contenido legal de una pagina HTML.

    Elimina scripts/estilos y navegacion comun; el resto se pasa tal cual a
    app.rag.chunker, que es quien detecta la estructura Titulo/Capitulo/
    Articulo a partir del texto plano.
    """
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "nav", "header", "footer"]):
        tag.decompose()

    return soup.get_text(separator="\n")
