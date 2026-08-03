from io import BytesIO

import pdfplumber


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extrae el texto de un PDF de ley, pagina por pagina, en orden.

    pdfplumber se usa en vez de pypdf porque maneja mejor el layout en
    columnas de algunos PDFs legales; si el texto sale desordenado para un
    documento en particular, revisar page.extract_text(layout=True).
    """
    pages_text = []
    with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            pages_text.append(text)
    return "\n".join(pages_text)
