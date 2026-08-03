import re
import unicodedata
from dataclasses import dataclass, field

# La linea completa despues de TITULO/CAPITULO/SECCION debe ser SOLO un
# ordinal reconocido (nada de texto extra), validado por _HEADER_LABEL_RE
# mas abajo via _match_header(). Bug real encontrado con la Ley de Salud del
# Estado de Chiapas (fuente: Consejeria Juridica): el regex original de una
# sola palabra (`[A-Z0-9]+`) tenia dos problemas sobre este documento --
# (a) esta ley tiene titulos con ordinal COMPUESTO ("TITULO DECIMO", "TITULO
# DECIMO PRIMERO", ..., "TITULO DECIMO SEXTO", 7 titulos distintos), y el
# regex de una sola palabra solo capturaba "DECIMO", colapsando 180 de 289
# chunks (62%) bajo el mismo valor de metadata `titulo="DECIMO"`; (b) frases
# de contenido normal que mencionan "TITULO"/"CAPITULO" a mitad de oracion
# ("...SERA SANCIONADA EN LOS TERMINOS PREVISTOS POR EL TITULO DECIMO
# QUINTO DE ESTA LEY.", Articulo 254) se trataban como si fueran un
# encabezado nuevo, truncando el articulo activo. Exigir que la linea
# COMPLETA sea solo el ordinal (sin texto antes ni despues) resuelve ambos:
# una cita a mitad de oracion nunca es la linea completa por si sola.
TITULO_RE = re.compile(r"^\s*TITULO\s+(.+?)\s*$", re.IGNORECASE)
CAPITULO_RE = re.compile(r"^\s*CAPITULO\s+(.+?)\s*$", re.IGNORECASE)
SECCION_RE = re.compile(r"^\s*SECCION\s+(.+?)\s*$", re.IGNORECASE)

# Ordinales en masculino (TITULO/CAPITULO/ARTICULO son masculinos en
# espanol: "TITULO PRIMERO") y en femenino (SECCION es femenino: "SECCION
# PRIMERA", nunca "SECCION PRIMERO"). Bug real encontrado con la Ley del
# Servicio Civil del Estado y los Municipios de Chiapas (fuente: Consejeria
# Juridica): la lista original solo tenia las formas masculinas, asi que
# NINGUN encabezado "SECCION PRIMERA"/"SECCION SEGUNDA"/etc. (7 de 9
# secciones del documento) matcheaba _HEADER_LABEL_RE en absoluto -- la linea
# completa caia al flujo de contenido normal (se descartaba si no habia
# articulo activo, o se pegaba como contenido del articulo activo si lo
# habia) y el metadata `seccion` de los articulos bajo esos encabezados se
# quedaba con el valor viejo (o None) en vez de actualizarse.
_ORDINAL_WORD = (
    r"PRIMERO|SEGUNDO|TERCERO|CUARTO|QUINTO|SEXTO|SEPTIMO|OCTAVO|NOVENO|"
    r"DECIMO|UNICO|"
    r"PRIMERA|SEGUNDA|TERCERA|CUARTA|QUINTA|SEXTA|SEPTIMA|OCTAVA|NOVENA|"
    r"DECIMA|UNICA|"
    r"BIS|TER|SIC|[IVXLCDM]+|\d+[A-Z]*"
)
# Bug real encontrado con el Codigo de Procedimientos Civiles para el Estado
# de Chiapas: TODO encabezado de Titulo/Capitulo/Seccion de este documento
# (mas de 100 encabezados reales en todo el texto: "TITULO PRIMERO.",
# "CAPITULO I.", "SECCION IV.", "TITULO DECIMO CUARTO.", etc.) cierra con un
# PUNTO final pegado al ultimo ordinal, sin espacio de por medio. El regex
# original no aceptaba ese punto (el label debia ser SOLO los ordinales, sin
# ningun caracter extra), asi que NINGUN encabezado real de este documento
# matcheaba en el camino estricto de _match_header, y el camino flexible
# (_ORDINAL_PREFIX_RE) tampoco los aceptaba porque exige que cada palabra
# ordinal este seguida de un espacio o del fin de linea, y aqui esta seguida
# de un punto. El resultado: current_titulo/current_capitulo/current_seccion
# se quedaban en None (o en el valor viejo) durante practicamente todo el
# documento, y el chunker caia de facto en un split ciego por articulo sin
# jerarquia -- exactamente el fallo que la fase de verificacion de este
# proyecto exige detectar (ver seccion "Que verificar", punto 1: el parser
# debe detectar Titulo > Capitulo > Seccion > Articulo, no caer a split
# ciego). Ademas, sin ningun encabezado real reconocido, una linea de
# contenido normal que por casualidad decia solo "TITULO DECIMO" (una
# referencia cruzada a mitad de documento, en su propia linea de PDF, SIN
# punto final) SI matcheaba el camino estricto de forma espuria y fijaba
# current_titulo="DECIMO" para el resto del documento completo -- una
# jerarquia incorrecta persistente, no solo ausente. Se acepta un punto
# final opcional pegado al ultimo ordinal (o al sufijo parentizado) como
# parte valida de un encabezado; el punto se descarta del label devuelto (ver
# `label.rstrip(".")` en _match_header) para no ensuciar la metadata/cita con
# un punto final.
_HEADER_LABEL_RE = re.compile(
    rf"^(?:{_ORDINAL_WORD})(?:\s+(?:{_ORDINAL_WORD}))*(?:\s*\([A-Z0-9]+\))?\.?$",
    re.IGNORECASE,
)

# Prefijo ordinal al inicio de la linea, usado para el match "flexible"
# (ver _match_header mas abajo) cuando el titulo descriptivo del
# Titulo/Capitulo/Seccion viene pegado en la MISMA linea que el ordinal en
# vez de en su propia linea separada, ej. "CAPITULO CUARTO DE LAS PRUEBAS" o
# "SECCION SEGUNDA DE LA CONFESIONAL" (ambos casos reales de la Ley del
# Servicio Civil). Solo se usa el prefijo ordinal como label; el resto de la
# linea (el titulo descriptivo) se descarta, igual que ya se descarta cuando
# ese titulo descriptivo viene en su propia linea (patron que ya funcionaba
# para la mayoria de los Titulo/Capitulo de este mismo documento).
#
# Cada palabra ordinal exige un limite de palabra despues (espacio o fin de
# linea via el lookahead "(?=\s|$)") para que la alternativa de numeral
# romano "[IVXLCDM]+" no consuma solo la primera letra de la SIGUIENTE
# palabra del titulo descriptivo. Bug real encontrado al escribir el test de
# regresion de este mismo caso: en "CAPITULO CUARTO DE LAS PRUEBAS", tras
# matchear "CUARTO" el grupo repetido intentaba una segunda palabra ordinal
# contra "DE LAS PRUEBAS", y "[IVXLCDM]+" matcheaba la "D" suelta de "DE"
# (D es un caracter romano valido), produciendo el label incorrecto "CUARTO
# D" en vez de "CUARTO".
_ORDINAL_PREFIX_RE = re.compile(
    rf"^(?:{_ORDINAL_WORD})(?=\s|$)(?:\s+(?:{_ORDINAL_WORD})(?=\s|$))*",
    re.IGNORECASE,
)


# Bug real encontrado con el Codigo Penal para el Estado de Chiapas: una
# fraccion enumerada con letra ("a) Que el delito se cometa con violencia
# fisica o moral.", "b) Que sea cometido por dos o mas personas", "c) Que
# sea cometido por un servidor publico o exservidor publico") puede ser la
# ULTIMA linea de contenido del Articulo 309 sin punto final -- typo real
# del propio PDF fuente, ya que el inciso a) de esa misma lista SI cierra
# con punto pero b) y c) no. Sin esta excepcion, _is_midsentence_line trataba
# el Articulo 310 real que viene justo despues como cita a mitad de oracion
# (la ultima linea "c) ... exservidor publico" no termina en '.', ':', ';'
# ni ')'), fusionando el Articulo 310 completo dentro del contenido del
# Articulo 309 -- un articulo entero desaparecido del chunking, exactamente
# el tipo de mala cita que la regla de oro del dominio legal prohibe. Un
# inciso enumerado (letra minuscula + ")", numeral romano + ".-", o digito +
# ")"/".- ") es, por su propia estructura de lista, una unidad ya cerrada
# aunque le falte el punto final; una cita a mitad de oracion cortada por
# pdfplumber (ver LEY_TORTURA_EXTRACTO_REAL en tests/test_chunker.py) nunca
# arranca con un marcador de lista como este, asi que no genera falsos
# negativos conocidos.
_ENUM_ITEM_RE = re.compile(r"^\s*(?:[a-z]|[ivxlcdm]+|\d+)[).]-?\s", re.IGNORECASE)


def _is_midsentence_line(current_articulo: str | None, current_content: list[str]) -> bool:
    """Misma heuristica que ya usa ARTICULO_RE mas abajo para distinguir un
    encabezado real de una cita a mitad de oracion que pdfplumber corto al
    inicio de una linea de PDF: si hay un articulo activo con contenido y su
    ultima linea no vacia NO cierra la oracion (no termina en '.', ':', ';'
    o ')'), esta linea es continuacion de esa oracion, no un encabezado
    nuevo. Excepcion: un inciso enumerado (ver _ENUM_ITEM_RE arriba) cuenta
    como cerrado aunque no termine en puntuacion, porque su propio marcador
    de lista ya delimita una unidad completa.
    """
    if current_articulo is None or not current_content:
        return False
    last_nonblank_line = next((l for l in reversed(current_content) if l.strip()), "")
    if last_nonblank_line == "":
        return False
    stripped = last_nonblank_line.rstrip()
    if stripped.endswith((".", ":", ";", ")")):
        return False
    if _ENUM_ITEM_RE.match(stripped.strip()):
        return False
    return True


def _match_header(
    line_re: re.Pattern,
    plain: str,
    current_articulo: str | None = None,
    current_content: list[str] | None = None,
) -> str | None:
    """Devuelve el ordinal si `plain` es un encabezado real, o None si la
    palabra clave aparece a mitad de una oracion de contenido normal.

    Primero intenta un match ESTRICTO: la linea consiste solo en la palabra
    clave + el ordinal, nada mas (caso mas comun y mas seguro). Si eso
    falla porque hay texto descriptivo pegado en la misma linea despues del
    ordinal (ej. "CAPITULO CUARTO DE LAS PRUEBAS"), intenta un match
    FLEXIBLE que solo toma el prefijo ordinal como label, pero unicamente si
    la linea no es una cita a mitad de oracion (mismo chequeo que ya protege
    a ARTICULO_RE de este caso).
    """
    match = line_re.match(plain)
    if not match:
        return None
    label = match.group(1)
    if _HEADER_LABEL_RE.match(label):
        # Ver comentario junto a _HEADER_LABEL_RE: el punto final opcional
        # (caso real del Codigo de Procedimientos Civiles, "TITULO PRIMERO.")
        # es parte valida del encabezado pero no debe quedar en la metadata
        # ni en la cita embebida.
        return label.rstrip(".")
    prefix_match = _ORDINAL_PREFIX_RE.match(label)
    if not prefix_match or not label[prefix_match.end():].strip():
        return None
    if _is_midsentence_line(current_articulo, current_content or []):
        return None
    return prefix_match.group(0)


# El numero de articulo puede venir seguido de un indicador ordinal antes del
# separador "." o "-": letras pegadas ("45o.-", "45a.-", ya cubiertas por
# [A-Z]* porque _strip_accents normaliza la "o" en superindice del indicador
# ordinal Unicode U+00BA a una "o" plana), o el simbolo de grado U+00B0
# ("ARTICULO 1\u00b0.- "), que NO tiene descomposicion NFKD y por lo tanto
# _strip_accents no lo quita. Este caso real aparecio en la Ley de Amnistia
# del Estado de Chiapas (fuente: Consejeria Juridica), donde pdfplumber
# extrae el indicador ordinal en superindice de la fuente del PDF como
# DEGREE SIGN en vez de una letra. El prefijo tambien acepta la abreviatura
# "ART." ademas de "ARTICULO" completo, y el separador final acepta uno o
# mas de "." / "-" para cubrir tanto "45.- " como "45. " (solo punto, sin
# guion). El prefijo tambien acepta el plural "ARTICULOS" (con "S" final)
# porque la Ley de Movilidad y Transporte del Estado de Chiapas (fuente:
# Consejeria Juridica) tiene un typo real en el propio PDF ("Articulos
# 145.- " para un unico articulo, no un rango) que sin esta "S" opcional no
# matcheaba nada: la linea completa quedaba pegada como contenido del
# Articulo 144 anterior y el Articulo 145 desaparecia por completo del
# chunking (numero de articulo faltante, cita rota en el chatbot). El sufijo
# de letra tambien puede venir separado del numero por un guion en vez de
# pegado ("278-A.-", "278-B.-"): bug real encontrado en el Codigo Fiscal del
# Estado de Chiapas (articulos adicionados via reforma que reutilizan el
# numero base con sufijo -A/-B en vez de "Bis"). Sin el grupo opcional
# "(?:-([A-Z]))?", el guion se consumia como parte del separador final y el
# sufijo de letra se perdia, dejando "278-A" y "278-B" indistinguibles de
# "278" en articulo_numero -- una mala cita exactamente del tipo que la
# regla de oro del dominio legal prohibe. El tercer grupo opcional
# "(?:\s+([A-Z]+))?" cubre otro sufijo real, esta vez separado del numero
# por un ESPACIO en vez de un guion: la Ley de Salud del Estado de Chiapas
# usa profusamente articulos "adicionados" con sufijo latino separado por
# espacio ("ARTICULO 117 BIS.-", "ARTICULO 125 QUATTOUR.-", hasta "ARTICULO
# 117 QUADRAGINTA.-"). Sin este grupo, esos 94 encabezados reales no
# matcheaban en absoluto y se fusionaban silenciosamente como contenido del
# articulo anterior (94 articulos "desaparecidos" del chunking). No se
# limita a una lista fija de sufijos latinos validos (BIS/TER/etc.) porque
# el propio PDF tiene typos reales ("QUATTOUR" en vez de "QUATTUOR"); se
# acepta cualquier palabra en mayusculas en esa posicion.
ARTICULO_RE = re.compile(
    r"^\s*(?:ARTICULOS?|ART\.)\s+(\d+[A-Z]*)(?:-([A-Z]))?(?:\s+([A-Z]+))?"
    r"\s*[\u00b0\u00ba]?\s*[.\-]+",
    re.IGNORECASE,
)

# Seccion de "TRANSITORIOS" al final de la ley (a veces con letras
# espaciadas por el PDF: "T R A N S I T O R I O"). No es un articulo
# normativo citable como los demas; su contenido (PRIMERO.-, SEGUNDO.-,
# firmas, fecha de decreto, etc.) NO debe quedar pegado al ultimo articulo
# real solo porque el chunker no reconoce el encabezado. Se trata como un
# limite que corta el articulo activo, igual que Titulo/Capitulo/Seccion,
# pero no genera su propio chunk (no hay campo de metadata para "articulos
# transitorios" en LegalChunk todavia).
#
# El prefijo opcional "ARTICULO(S) " cubre un bug real encontrado en el
# Codigo Civil para el Estado de Chiapas, Libro Cuarto (De las Obligaciones):
# el encabezado real de esta seccion en el propio documento es "ARTICULOS
# TRANSITORIOS" (dos palabras), no "TRANSITORIOS" a secas. Sin este prefijo
# opcional, la linea no matcheaba en absoluto y el chunker seguia leyendo
# ARTICULO_RE con normalidad sobre el contenido de la seccion -- que en este
# documento en particular resulto ser el problema real: los transitorios del
# decreto original de 1938 estan numerados con el mismo formato numerico que
# un articulo normativo real ("ART. 1.- ESTE CODIGO ENTRARA EN VIGOR...",
# "ART. 2.-", ..., "ART. 7.-"), a diferencia de la convencion mas comun de
# usar ordinales en palabra ("PRIMERO.-", "SEGUNDO.-") que ARTICULO_RE nunca
# matchea. Esto generaba 7 chunks fantasma con articulo_numero "1" al "7"
# atribuidos a Libro Cuarto (mala cita: esos numeros no son articulos reales
# de Libro Cuarto, son clausulas transitorias del decreto fundacional de todo
# el Codigo). Ver `past_transitorios` en chunk_legal_text mas abajo para la
# segunda mitad de la proteccion: una vez cruzado este limite, NINGUNA linea
# posterior (ARTICULO/TITULO/CAPITULO/SECCION o no) puede volver a abrir un
# chunk nuevo, sea cual sea el formato de numeracion que use el resto del
# apendice de transitorios historicos (este documento en particular sigue
# transcribiendo, tras el decreto original, los transitorios de cada decreto
# de reforma posterior hasta el final del archivo).
#
# El punto final opcional ("TRANSITORIOS.") cubre un bug real encontrado con
# la Ley de Fraccionamientos y Conjuntos Habitacionales para el Estado y los
# Municipios de Chiapas: el encabezado real de esta seccion en este PDF es
# "TRANSITORIOS." con punto final pegado (mismo tipo de convencion tipografica
# ya corregida para TITULO/CAPITULO/SECCION en _HEADER_LABEL_RE, ver
# comentario junto a esa constante mas arriba, motivado originalmente por el
# Codigo de Procedimientos Civiles). Sin este punto opcional, la linea no
# matcheaba en absoluto, past_transitorios nunca se activaba, y TODO el
# contenido de los transitorios (incluyendo firmas y fecha del decreto al
# final del archivo completo) se fusionaba silenciosamente como contenido
# del ultimo articulo real (Articulo 141) -- un chunk final contaminado con
# texto no normativo, mala cita del mismo tipo que la regla de oro del
# dominio legal prohibe.
TRANSITORIO_RE = re.compile(
    r"^\s*(?:ARTICULOS?\s+)?T\s*R\s*A\s*N\s*S\s*I\s*T\s*O\s*R\s*I\s*O\s*S?\s*\.?\s*$",
    re.IGNORECASE,
)

# Pie de pagina que pdfplumber intercala entre articulos en documentos de
# varias paginas (marca de tiempo de consulta + numero de pagina), ej.
# "17/10/2022 02:25 p.m. 4" o "14/10/2022 01:19 p.m. 16". Ya se documento en
# Fase 1 (Ley de Amnistia, 3 paginas) como ruido aceptable porque no
# matcheaba ningun limite y quedaba flotando dentro del articulo activo sin
# romper nada. Con documentos mas largos (Fase 2) el problema se vuelve real:
# esta linea se convierte en la "ultima linea de contenido" justo antes de un
# encabezado de articulo real, y como no termina en puntuacion, confundia la
# heuristica de "cita de articulo a mitad de oracion" (ver ARTICULO_RE mas
# abajo) haciendola tratar articulos reales como continuacion del anterior.
# Se descarta esta linea por completo (no se agrega a ningun chunk) en vez de
# tratarla como limite o como contenido.
FOOTER_RE = re.compile(
    r"^\s*\d{1,2}/\d{1,2}/\d{4}\s+\d{1,2}:\d{2}\s*[ap]\.m\.\s*\d*\s*$",
    re.IGNORECASE,
)

# Otro tipo de ruido de salto de pagina, distinto de FOOTER_RE (que solo
# cubre el formato "fecha hora a.m./p.m. numero"). Bug real encontrado con
# la Ley de Salud del Estado de Chiapas (136 paginas): pdfplumber extrae, al
# inicio de CADA pagina, un numero de pagina suelto ("21") seguido del
# nombre de la ley repetido como encabezado ("LEY DE SALUD DEL ESTADO DE
# CHIAPAS"). Como estas dos lineas no matcheaban ningun limite conocido,
# quedaban pegadas como contenido normal del articulo activo, y la segunda
# (que no termina en '.', ':', ';' ni ')') se convertia en la
# "ultima linea de contenido" que usa la heuristica de "cita a mitad de
# oracion" de ARTICULO_RE mas abajo -- asi que CUALQUIER articulo real que
# empezara justo despues de un salto de pagina se trataba como referencia a
# mitad de oracion en vez de limite nuevo, fusionandolo dentro del articulo
# anterior (caso real: el Articulo 41 completo desaparecia fusionado dentro
# del Articulo 40). El nombre de la ley repetido se arma dinamicamente a
# partir de `document_nombre` (el mismo parametro que ya recibe
# chunk_legal_text) en vez de una lista fija, para que esta proteccion
# aplique a cualquier ley, no solo a la de Salud.
_PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")


def _strip_accents(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


@dataclass
class LegalChunk:
    articulo_numero: str | None
    titulo: str | None
    capitulo: str | None
    seccion: str | None
    content: str
    document_nombre: str = ""

    def to_embedding_text(self, content: str | None = None) -> str:
        """Texto con contexto estructural incluido, mejora retrieval y citas.

        Acepta un `content` opcional distinto de self.content para el caso en
        que un articulo real sea demasiado largo para el modelo de
        embeddings y haya que sub-dividirlo en piezas mas chicas (ver
        app.rag.embeddings._split_content_for_embedding): cada pieza sigue
        llevando el mismo encabezado estructural (ley/titulo/capitulo/
        articulo) aunque el contenido embebido sea solo una parte del
        articulo completo.
        """
        parts = [self.document_nombre]
        if self.titulo:
            parts.append(f"Titulo {self.titulo}")
        if self.capitulo:
            parts.append(f"Capitulo {self.capitulo}")
        if self.articulo_numero:
            parts.append(f"Articulo {self.articulo_numero}")
        header = ", ".join(p for p in parts if p)
        body = self.content if content is None else content
        return f"{header}: {body}" if header else body


def chunk_legal_text(raw_text: str, document_nombre: str = "") -> list[LegalChunk]:
    """Parte un documento legal respetando Titulo > Capitulo > Seccion > Articulo.

    Cada ARTICULO es la unidad natural de chunk. Lineas antes del primer
    articulo (preambulo) se ignoran para efectos de chunk (no tienen
    articulo_numero al que citar).
    """
    lines = raw_text.splitlines()

    # Ver docstring de _PAGE_NUMBER_RE: nombre de la ley repetido en cada
    # salto de pagina, armado a partir de este mismo document_nombre.
    repeated_title_plain = _strip_accents(document_nombre).strip().upper()

    chunks: list[LegalChunk] = []
    current_titulo: str | None = None
    current_capitulo: str | None = None
    current_seccion: str | None = None
    current_articulo: str | None = None
    current_content: list[str] = []

    # Una vez que se cruza el limite de TRANSITORIO_RE, ningun contenido
    # posterior puede volver a abrir un chunk nuevo, sin importar que formato
    # de numeracion use (ver comentario largo junto a TRANSITORIO_RE arriba
    # para el bug real que motivo esto: el Codigo Civil, Libro Cuarto, numera
    # sus propios transitorios como "ART. 1.- ", "ART. 2.- ", etc., formato
    # identico al de un articulo normativo real, y ademas sigue transcribiendo
    # los transitorios de cada decreto de reforma posterior hasta el final del
    # archivo). En un documento legal mexicano los TRANSITORIOS son siempre la
    # ultima seccion; no hay caso real conocido de un Titulo/Capitulo/Seccion/
    # Articulo normativo legitimo apareciendo despues.
    past_transitorios = False

    def flush() -> None:
        if current_articulo is not None and current_content:
            chunks.append(
                LegalChunk(
                    articulo_numero=current_articulo,
                    titulo=current_titulo,
                    capitulo=current_capitulo,
                    seccion=current_seccion,
                    content="\n".join(current_content).strip(),
                    document_nombre=document_nombre,
                )
            )

    for line in lines:
        plain = _strip_accents(line)

        if past_transitorios:
            continue

        if FOOTER_RE.match(plain):
            continue

        if _PAGE_NUMBER_RE.match(plain):
            continue

        if repeated_title_plain and plain.strip().upper() == repeated_title_plain:
            continue

        titulo_label = _match_header(TITULO_RE, plain, current_articulo, current_content)
        if titulo_label is not None:
            flush()
            current_titulo = titulo_label
            current_articulo = None
            current_content = []
            continue

        capitulo_label = _match_header(CAPITULO_RE, plain, current_articulo, current_content)
        if capitulo_label is not None:
            flush()
            current_capitulo = capitulo_label
            current_articulo = None
            current_content = []
            continue

        seccion_label = _match_header(SECCION_RE, plain, current_articulo, current_content)
        if seccion_label is not None:
            flush()
            current_seccion = seccion_label
            current_articulo = None
            current_content = []
            continue

        if TRANSITORIO_RE.match(plain):
            flush()
            current_articulo = None
            current_content = []
            past_transitorios = True
            continue

        match = ARTICULO_RE.match(plain)
        if match:
            # Bug real encontrado con la Ley Estatal para Prevenir y Sancionar
            # la Tortura: un articulo puede CITAR a otro articulo por numero
            # ("...SE ESTARA A LO ESTABLECIDO EN LA PARTE FINAL DEL\nARTICULO
            # 4o. DE ESTE ORDENAMIENTO.") y pdfplumber corta esa cita justo al
            # inicio de una linea de PDF, haciendo que ARTICULO_RE la matchee
            # como si fuera un encabezado real de articulo nuevo. Sin este
            # chequeo, el articulo activo se trunca a la mitad y se genera un
            # chunk fantasma (numero de articulo duplicado/roto, contenido de
            # una sola linea) -- exactamente el tipo de "chunk mal atribuido"
            # que es la regla de oro a evitar. Un encabezado real de articulo
            # SIEMPRE llega despues de que el articulo anterior cerro su idea
            # (la ultima linea de contenido NO vacia termina en '.', ':', ';'
            # o ')'); una cita a mitad de oracion no. Se usa esa senal para
            # distinguir ambos casos: si hay un articulo activo con contenido
            # y su ultima linea no vacia NO cierra la oracion, se trata como
            # texto normal (parte del articulo activo) en vez de como limite
            # nuevo. Se ignoran lineas en blanco al buscar esa ultima linea
            # (el SAMPLE_LAW sintetico separa articulos con una linea en
            # blanco; sin este filtro, esa linea vacia "termina" en nada y el
            # chequeo confundia un limite real de articulo con una cita). El
            # ')' se acepta como cierre valido ademas de '.', ':' y ';' porque
            # esta misma Ley de Tortura cierra articulos reformados con una
            # anotacion legislativa entre parentesis ("(REFORMADO, P.O. 17 DE
            # SEPTIEMBRE DE 2012)") antes del siguiente ARTICULO real; sin
            # aceptar ')' como cierre, esa anotacion (que termina en parentesis,
            # no en punto) disparaba el mismo falso positivo que la cita a
            # mitad de oracion, fusionando articulos reales de mas.
            if _is_midsentence_line(current_articulo, current_content):
                current_content.append(line)
                continue

            flush()
            current_articulo = match.group(1)
            if match.group(2):
                current_articulo = f"{current_articulo}-{match.group(2)}"
            if match.group(3):
                current_articulo = f"{current_articulo} {match.group(3)}"
            current_content = [line]
            continue

        if current_articulo is not None:
            current_content.append(line)

    flush()
    return chunks
