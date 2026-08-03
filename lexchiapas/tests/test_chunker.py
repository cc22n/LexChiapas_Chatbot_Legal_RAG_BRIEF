from app.rag.chunker import chunk_legal_text

SAMPLE_LAW = """
LEY DE EJEMPLO DEL ESTADO DE CHIAPAS

TITULO PRIMERO
DISPOSICIONES GENERALES

CAPITULO I
Objeto de la Ley

ARTICULO 1.- La presente ley tiene por objeto regular el ejemplo.
Es de orden publico e interes social.

ARTICULO 2.- Para efectos de esta ley se entiende por:
I. Ejemplo: lo que se usa para probar el chunker.

CAPITULO II
Del Ambito de Aplicacion

ARTICULO 3.- Esta ley aplica en todo el territorio del Estado de Chiapas.
"""


def test_chunks_respect_article_boundaries():
    chunks = chunk_legal_text(SAMPLE_LAW, document_nombre="Ley de Ejemplo")

    assert [c.articulo_numero for c in chunks] == ["1", "2", "3"]


def test_chunks_carry_titulo_and_capitulo_metadata():
    chunks = chunk_legal_text(SAMPLE_LAW, document_nombre="Ley de Ejemplo")

    articulo_1 = next(c for c in chunks if c.articulo_numero == "1")
    assert articulo_1.titulo == "PRIMERO"
    assert articulo_1.capitulo == "I"

    articulo_3 = next(c for c in chunks if c.articulo_numero == "3")
    assert articulo_3.capitulo == "II"


def test_embedding_text_includes_structural_context():
    chunks = chunk_legal_text(SAMPLE_LAW, document_nombre="Ley de Ejemplo")
    articulo_1 = next(c for c in chunks if c.articulo_numero == "1")

    embedding_text = articulo_1.to_embedding_text()
    assert "Ley de Ejemplo" in embedding_text
    assert "Articulo 1" in embedding_text


def test_preamble_before_first_article_is_ignored():
    chunks = chunk_legal_text(SAMPLE_LAW, document_nombre="Ley de Ejemplo")

    for chunk in chunks:
        assert "LEY DE EJEMPLO" not in chunk.content


# Extracto real (verbatim) de la Ley de Amnistia del Estado de Chiapas
# (Periodico Oficial No. 296, Decreto 129, 4 de febrero de 1994), descargada
# como PDF real de
# https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/Leyes/pdf/LEY%20DE%20AMNISTIA.pdf
# y extraida con ingestion/parsers/pdf_parser.py (extract_text_from_pdf).
# Sirve de regresion real para dos bugs encontrados al validar
# app.rag.chunker contra este documento (no contra el SAMPLE_LAW sintetico
# de arriba):
#
# 1. El PDF real usa un indicador ordinal despues del numero de articulo
#    ("ARTICULO 1o.- ") que pdfplumber extrae como DEGREE SIGN (U+00B0,
#    escrito abajo con el escape \u00b0 para mantener este archivo en ASCII
#    puro), no como una letra "o" ni como una tilde que _strip_accents
#    normalice. El ARTICULO_RE original (que exigia digito seguido directo
#    de [.\-]) no matcheaba esta linea y el articulo se perdia por completo.
# 2. La seccion "T R A N S I T O R I O" (con letras espaciadas, formato
#    comun en PDFs legales viejos) no era reconocida como limite, asi que su
#    contenido (PRIMERO.-, SEGUNDO.-, etc.) quedaba pegado como parte del
#    contenido del ultimo articulo real -- un chunk mal atribuido.
LEY_AMNISTIA_EXTRACTO_REAL = (
    "LEY DE AMNISTIA.\n"
    "ARTICULO 1\u00b0.- SE DECRETA AMNISTIA EN FAVOR DE TODAS LAS\n"
    "PERSONAS EN CONTRA DE QUIENES SE HAYAN EJERCITADO O PUDIERE\n"
    "EJERCITARSE ACCION PENAL ANTE LOS TRIBUNALES DEL FUERO COMUN.\n"
    "ARTICULO 2\u00b0.- LOS BENEFICIOS DERIVADOS DEL ARTICULO ANTERIOR\n"
    "ALCANZARAN A TODOS LOS INDIVIDUOS QUE SE ENCUENTREN DENTRO O\n"
    "FUERA DEL ESTADO O DEL PAIS.\n"
    "T R A N S I T O R I O\n"
    "PRIMERO.- ESTA LEY ENTRARA EN VIGOR EL DIA DE SU PUBLICACION EN\n"
    "EL PERIODICO OFICIAL DEL ESTADO.\n"
)


def test_real_document_article_with_degree_sign_ordinal_is_detected():
    chunks = chunk_legal_text(LEY_AMNISTIA_EXTRACTO_REAL, document_nombre="Ley de Amnistia")

    assert [c.articulo_numero for c in chunks] == ["1", "2"]


def test_real_document_transitorio_section_does_not_leak_into_last_articulo():
    chunks = chunk_legal_text(LEY_AMNISTIA_EXTRACTO_REAL, document_nombre="Ley de Amnistia")

    articulo_2 = next(c for c in chunks if c.articulo_numero == "2")
    assert "TRANSITORIO" not in articulo_2.content
    assert "PRIMERO" not in articulo_2.content


# Extracto real (verbatim) de la Ley Estatal para Prevenir y Sancionar la
# Tortura del Estado de Chiapas, descargada como PDF real de
# https://consejeriajuridica.chiapas.gob.mx/Marco_Juridico/Leyes/pdf/LEY%20ESTATAL%20PARA%20PREVENIR%20Y%20SANCIONAR%20LA%20TORTURA%20DEL%20ESTADO%20DE%20CHIAPAS.pdf
# y extraida con ingestion/parsers/pdf_parser.py (extract_text_from_pdf).
# Sirve de regresion real para un tercer bug de chunker (el primero y segundo
# fueron el DEGREE SIGN y TRANSITORIO, cubiertos arriba con
# LEY_AMNISTIA_EXTRACTO_REAL):
#
# 3. El ARTICULO 10 real de esta ley CITA al ARTICULO 4 por numero dentro de
#    su propio texto ("...SE ESTARA A LO ESTABLECIDO EN LA PARTE FINAL DEL
#    ARTICULO 4o. DE ESTE ORDENAMIENTO."), y pdfplumber corta esa cita justo
#    al inicio de una linea del PDF (la palabra "ARTICULO" queda al principio
#    de su propia linea). Sin proteccion, ARTICULO_RE matcheaba esa cita como
#    si fuera el encabezado de un articulo nuevo, truncando el contenido real
#    del Articulo 10 y generando un chunk fantasma con numero "4o" (distinto
#    del Articulo 4 real, que ya existe con su propio contenido correcto) y
#    contenido de una sola linea ("ARTICULO 4o. DE ESTE ORDENAMIENTO."). El
#    indicador ordinal en este documento en particular es el caracter
#    MASCULINE ORDINAL INDICATOR (U+00BA, escrito abajo con el escape
#    \u00ba, igual que \u00b0 arriba, para mantener este archivo en ASCII
#    puro), distinto del DEGREE SIGN (U+00B0) de la Ley de Amnistia, pero ya
#    cubierto por la misma clase de caracteres opcional en ARTICULO_RE.
LEY_TORTURA_EXTRACTO_REAL = (
    "ARTICULO 10.- EL SERVIDOR PUBLICO QUE EN EL EJERCICIO DE SUS\n"
    "FUNCIONES CONOZCA DE UN HECHO DE TORTURA, ESTA OBLIGADO A\n"
    "DENUNCIARLO DE INMEDIATO, SI NO LO HICIERE SE LE IMPONDRA DE\n"
    "TRES MESES A TRES A\u00d1OS DE PENA PRIVATIVA DE LIBERTAD, Y DE\n"
    "QUINCE A SETENTA DIAS DE MULTA, SIN PERJUICIO DE LOS QUE\n"
    "ESTABLEZCAN OTRAS LEYES, PARA LA DETERMINACION DE LOS DIAS DE\n"
    "MULTA, SE ESTARA A LO ESTABLECIDO EN LA PARTE FINAL DEL\n"
    "ARTICULO 4\u00ba. DE ESTE ORDENAMIENTO.\n"
    "ARTICULO 11.- EN TODO LO PREVISTO POR ESTA LEY, SERAN APLICABLES\n"
    "LAS DISPOSICIONES DE LOS CODIGOS PENAL Y DE PROCEDIMIENTOS\n"
    "PENALES DEL ESTADO DE CHIAPAS.\n"
)


def test_real_document_midsentence_article_reference_does_not_split_chunk():
    chunks = chunk_legal_text(LEY_TORTURA_EXTRACTO_REAL, document_nombre="Ley de Tortura")

    assert [c.articulo_numero for c in chunks] == ["10", "11"]

    articulo_10 = next(c for c in chunks if c.articulo_numero == "10")
    assert "ARTICULO 4" in articulo_10.content
    assert "DE ESTE ORDENAMIENTO" in articulo_10.content


# Extracto real (verbatim) de la Ley de Movilidad y Transporte del Estado de
# Chiapas, descargada como PDF real de
# https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/Leyes/pdf/LEY%20DE%20MOVILIDAD%20Y%20TRANSPORTE%20DEL%20ESTADO%20DE%20CHIAPAS.pdf
# y extraida con ingestion/parsers/pdf_parser.py (extract_text_from_pdf).
# Sirve de regresion real para un cuarto bug de chunker (el primero, segundo
# y tercero fueron el DEGREE SIGN, TRANSITORIO, y la cita a mitad de
# oracion, cubiertos arriba):
#
# 4. El propio PDF tiene un typo real en el encabezado del Articulo 145
#    ("Articulos 145.- " en plural, para un unico articulo, no un rango).
#    ARTICULO_RE original exigia "ARTICULO" exacto (sin "S" final) seguido
#    de espacio, asi que esta linea no matcheaba como encabezado de articulo
#    nuevo: quedaba pegada como contenido del Articulo 144 anterior y el
#    Articulo 145 desaparecia por completo del chunking.
LEY_MOVILIDAD_EXTRACTO_REAL = (
    "Articulo 144.- En caso de emergencia sanitaria, para garantizar la salud propia y de los\n"
    "usuarios, los concesionarios, permisionarios y operadores deberan cumplir el protocolo\n"
    "de seguridad que emitan las autoridades en materia de salud.\n"
    "Articulos 145.- Los administradores de las terminales, en caso de emergencia sanitaria,\n"
    "deberan ejecutar los protocolos que emitan la Secretaria y las autoridades de salud.\n"
    "Articulo 146.- En caso de emergencia sanitaria, los usuarios del servicio publico de\n"
    "transporte deberan cumplir los protocolos emitidos por las autoridades en materia de\n"
    "salud.\n"
)


def test_real_document_plural_articulos_typo_is_still_detected():
    chunks = chunk_legal_text(LEY_MOVILIDAD_EXTRACTO_REAL, document_nombre="Ley de Movilidad")

    assert [c.articulo_numero for c in chunks] == ["144", "145", "146"]

    articulo_145 = next(c for c in chunks if c.articulo_numero == "145")
    assert "administradores de las terminales" in articulo_145.content


# Extracto real (verbatim) de la Ley de Salud del Estado de Chiapas,
# descargada como PDF real de
# https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/Leyes/pdf/LEY%20DE%20SALUD%20DEL%20ESTADO%20DE%20CHIAPAS.pdf
# y extraida con ingestion/parsers/pdf_parser.py (extract_text_from_pdf).
# Sirve de regresion real para dos bugs adicionales de chunker encontrados en
# este documento (los primeros cuatro fueron el DEGREE SIGN, TRANSITORIO, la
# cita a mitad de oracion, y el typo plural de "Articulos", cubiertos arriba):
#
# 5. TITULO_RE/CAPITULO_RE originales solo capturaban la PRIMERA palabra del
#    ordinal ("DECIMO" en vez de "DECIMO QUINTO"), y ademas matcheaban
#    referencias a mitad de oracion ("...SERA SANCIONADA EN LOS TERMINOS
#    PREVISTOS POR EL\nTITULO DECIMO QUINTO DE ESTA LEY.") como si fueran un
#    encabezado nuevo, cortando el Articulo 254 a la mitad. El encabezado
#    real de "TITULO DECIMO QUINTO" (linea completa, sin texto extra) llega
#    varias lineas despues, cruzando un salto de pagina real (numero de
#    pagina suelto "111" + nombre de la ley repetido).
# 6. ARTICULO_RE original no soportaba sufijos ordinales latinos separados
#    por ESPACIO del numero ("ARTICULO 254 BIS.-"), solo pegados o con
#    guion -- este articulo desaparecia fusionado dentro del Articulo 254.
LEY_SALUD_EXTRACTO_REAL = (
    "ARTICULO 254.- LA OPOSICION A LAS ACTIVIDADES A QUE SE CONTRAE EL\n"
    "PRESENTE CAPITULO Y, SIN PERJUICIO DE LO DISPUESTO POR OTROS\n"
    "ORDENAMIENTOS, SERA SANCIONADA EN LOS TERMINOS PREVISTOS POR EL\n"
    "TITULO DECIMO QUINTO DE ESTA LEY.\n"
    "111\n"
    "LEY DE SALUD DEL ESTADO DE CHIAPAS\n"
    "TITULO DECIMO QUINTO\n"
    "MEDIDAS DE SEGURIDAD Y SANCIONES\n"
    "CAPITULO I\n"
    "DE LAS MEDIDAS DE SEGURIDAD SANITARIA.\n"
    "ARTICULO 254 BIS.- SE CONSIDERAN MEDIDAS DE SEGURIDAD LAS\n"
    "DISPOSICIONES QUE DICTE LA AUTORIDAD SANITARIA.\n"
)


def test_real_document_midsentence_titulo_reference_does_not_split_chunk():
    chunks = chunk_legal_text(
        LEY_SALUD_EXTRACTO_REAL, document_nombre="Ley de Salud del Estado de Chiapas"
    )

    assert [c.articulo_numero for c in chunks] == ["254", "254 BIS"]

    articulo_254 = next(c for c in chunks if c.articulo_numero == "254")
    assert "TITULO DECIMO QUINTO DE ESTA LEY" in articulo_254.content
    assert "111" not in articulo_254.content
    assert "LEY DE SALUD DEL ESTADO DE CHIAPAS" not in articulo_254.content


def test_real_document_compound_titulo_and_space_separated_articulo_suffix():
    chunks = chunk_legal_text(
        LEY_SALUD_EXTRACTO_REAL, document_nombre="Ley de Salud del Estado de Chiapas"
    )

    articulo_254_bis = next(c for c in chunks if c.articulo_numero == "254 BIS")
    assert articulo_254_bis.titulo == "DECIMO QUINTO"
    assert articulo_254_bis.capitulo == "I"


# Extracto real (verbatim) de la Ley del Servicio Civil del Estado y los
# Municipios de Chiapas, descargada como PDF real de
# https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/Leyes/pdf/LEY_DEL_SERVICIO_CIVIL_DEL_ESTADO_Y_LOS_MUNICIPIOS_DE_CHIAPAS.pdf
# y extraida con ingestion/parsers/pdf_parser.py (extract_text_from_pdf).
# Sirve de regresion real para dos bugs adicionales de chunker encontrados en
# este documento (los anteriores fueron el DEGREE SIGN, TRANSITORIO, la cita
# a mitad de oracion, el typo plural de "Articulos", y el ordinal compuesto,
# cubiertos arriba):
#
# 7. SECCION es femenino en espanol ("SECCION PRIMERA", "SECCION SEGUNDA"),
#    a diferencia de TITULO/CAPITULO/ARTICULO que son masculinos ("TITULO
#    PRIMERO"). _ORDINAL_WORD original solo tenia las formas masculinas, asi
#    que NINGUN encabezado "SECCION PRIMERA"/"SECCION SEGUNDA"/etc. (7 de 9
#    secciones de este documento) era reconocido como encabezado real -- la
#    linea completa caia al flujo de contenido normal.
# 8. Varios CAPITULO (y dos SECCION) de este documento tienen el titulo
#    descriptivo pegado en la MISMA linea que el ordinal, en vez de en su
#    propia linea separada (patron que si funcionaba antes): "CAPITULO
#    CUARTO DE LAS PRUEBAS", "SECCION SEGUNDA DE LA CONFESIONAL". El match
#    estricto exige que la linea completa sea solo el ordinal, asi que estos
#    encabezados tampoco eran reconocidos y su texto se colaba como
#    contenido del articulo activo anterior (o se perdia si no habia
#    articulo activo), dejando el metadata capitulo/seccion desactualizado
#    para todos los articulos siguientes hasta el proximo encabezado que si
#    matcheara.
LEY_SERVICIO_CIVIL_EXTRACTO_REAL = (
    "(ADICIONADO CON LOS ARTICULOS QUE LO INTEGRAN, P.O. 31 DE\n"
    "DICIEMBRE DE 2016)\n"
    "CAPITULO CUARTO DE LAS PRUEBAS\n"
    "(ADICIONADA CON LOS ARTICULOS QUE LA INTEGRAN, P.O. 31 DE\n"
    "DICIEMBRE DE 2016)\n"
    "SECCION PRIMERA REGLAS GENERALES\n"
    "(ADICIONADO, P.O. 31 DE DICIEMBRE DE 2016)\n"
    "ARTICULO 115.- EL DIA Y HORA DE LA AUDIENCIA SE RECIBIRAN LAS\n"
    "PRUEBAS.\n"
    "(ADICIONADA CON LOS ARTICULOS QUE LA INTEGRAN, P.O. 31 DE\n"
    "DICIEMBRE DE 2016)\n"
    "SECCION SEGUNDA DE LA CONFESIONAL\n"
    "(ADICIONADO, P.O. 31 DE DICIEMBRE DE 2016)\n"
    "ARTICULO 122.- CADA PARTE PODRA SOLICITAR SE CITE A SU\n"
    "CONTRAPARTE PARA QUE CONCURRA A ABSOLVER POSICIONES.\n"
)


def test_real_document_feminine_seccion_ordinal_is_detected():
    chunks = chunk_legal_text(
        LEY_SERVICIO_CIVIL_EXTRACTO_REAL,
        document_nombre="Ley del Servicio Civil del Estado y los Municipios de Chiapas",
    )

    assert [c.articulo_numero for c in chunks] == ["115", "122"]

    articulo_122 = next(c for c in chunks if c.articulo_numero == "122")
    assert articulo_122.seccion == "SEGUNDA"


def test_real_document_capitulo_and_seccion_with_trailing_title_same_line():
    chunks = chunk_legal_text(
        LEY_SERVICIO_CIVIL_EXTRACTO_REAL,
        document_nombre="Ley del Servicio Civil del Estado y los Municipios de Chiapas",
    )

    articulo_115 = next(c for c in chunks if c.articulo_numero == "115")
    assert articulo_115.capitulo == "CUARTO"
    assert articulo_115.seccion == "PRIMERA"
    assert "CAPITULO CUARTO" not in articulo_115.content
    assert "SECCION PRIMERA" not in articulo_115.content
    assert "DE LAS PRUEBAS" not in articulo_115.content
    assert "REGLAS GENERALES" not in articulo_115.content


# Extracto real (verbatim, recortado) del Codigo Civil para el Estado de
# Chiapas, Libro Cuarto (De las Obligaciones), descargado como PDF real de
# https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/Leyes/pdf/CODIGO%20CIVIL%20PARA%20EL%20ESTADO%20DE%20CHIAPAS.pdf
# y extraido con ingestion/parsers/pdf_parser.py (extract_text_from_pdf).
# Sirve de regresion real para un noveno bug de chunker (los anteriores
# fueron el DEGREE SIGN, TRANSITORIO, la cita a mitad de oracion, el typo
# plural de "Articulos", el ordinal compuesto, la SECCION femenina, y el
# titulo pegado en la misma linea, cubiertos arriba):
#
# 9. El encabezado real de la seccion final de este documento es "ARTICULOS
#    TRANSITORIOS" (dos palabras), no "TRANSITORIOS" a secas, asi que el
#    TRANSITORIO_RE original no lo reconocia como limite. Peor aun: los
#    transitorios del decreto original de 1938 estan numerados con el mismo
#    formato NUMERICO que un articulo normativo real ("ART. 1.- ESTE CODIGO
#    ENTRARA EN VIGOR...", "ART. 2.-", etc.), a diferencia de la convencion
#    mas comun de ordinales en palabra ("PRIMERO.-", "SEGUNDO.-") que
#    ARTICULO_RE nunca matchea. Sin el prefijo opcional "ARTICULO(S) " en
#    TRANSITORIO_RE y sin el nuevo estado `past_transitorios` en
#    chunk_legal_text (que suprime CUALQUIER limite u articulo posterior una
#    vez cruzada la seccion de transitorios), estas lineas generaban 7 chunks
#    fantasma con articulo_numero "1" al "7" atribuidos a Libro Cuarto -- una
#    mala cita, porque esos numeros no son articulos reales de este Libro,
#    son clausulas transitorias del decreto fundacional de todo el Codigo.
LIBRO_CUARTO_TRANSITORIOS_EXTRACTO_REAL = (
    "ART. 3016.- LAS INSCRIPCIONES PREVENTIVAS, SE CANCELARAN NO\n"
    "SOLAMENTE CUANDO SE EXTINGA EL DERECHO INSCRITO, SINO TAMBIEN\n"
    "CUANDO ESA INSCRIPCION SE CONVIERTA EN DEFINITIVA.\n"
    "ARTICULOS TRANSITORIOS\n"
    "ART. 1.- ESTE CODIGO ENTRARA EN VIGOR EL DIA CINCO DE FEBRERO DE\n"
    "MIL NOVECIENTOS TREINTA Y OCHO.\n"
    "ART. 2.- SUS DISPOSICIONES REGIRAN LOS EFECTOS JURIDICOS DE LOS\n"
    "ACTOS ANTERIORES A SU VIGENCIA, SI CON ELLOS NO SE VIOLAN\n"
    "DERECHOS ADQUIRIDOS.\n"
    "TITULO PRIMERO\n"
    "ARTICULO 8.- ESTE ARTICULO NO DEBE GENERAR UN CHUNK NUEVO.\n"
)


def test_real_document_plural_articulos_transitorios_header_suppresses_numeric_transitorios():
    chunks = chunk_legal_text(
        LIBRO_CUARTO_TRANSITORIOS_EXTRACTO_REAL,
        document_nombre=(
            "Codigo Civil para el Estado de Chiapas - Libro Cuarto (De las Obligaciones)"
        ),
    )

    assert [c.articulo_numero for c in chunks] == ["3016"]

    articulo_3016 = chunks[0]
    assert "ARTICULOS TRANSITORIOS" not in articulo_3016.content
    assert "ART. 1" not in articulo_3016.content
    assert "ART. 2" not in articulo_3016.content


def test_real_document_nothing_reopens_a_chunk_after_transitorios_boundary():
    chunks = chunk_legal_text(
        LIBRO_CUARTO_TRANSITORIOS_EXTRACTO_REAL,
        document_nombre=(
            "Codigo Civil para el Estado de Chiapas - Libro Cuarto (De las Obligaciones)"
        ),
    )

    # Ni el "TITULO PRIMERO" ni el "ARTICULO 8.-" que aparecen despues de la
    # seccion de transitorios deben producir un chunk nuevo.
    assert not any(c.articulo_numero == "8" for c in chunks)


# Extracto real (verbatim) del Codigo Penal para el Estado de Chiapas,
# descargado como PDF real de
# https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0012.pdf?v=NDM=
# y extraido con ingestion/parsers/pdf_parser.py (extract_text_from_pdf).
# Sirve de regresion real para un decimo bug de chunker (los anteriores
# fueron el DEGREE SIGN, TRANSITORIO, la cita a mitad de oracion, el typo
# plural de "Articulos", el ordinal compuesto, la SECCION femenina, el
# titulo pegado en la misma linea, y "ARTICULOS TRANSITORIOS", cubiertos
# arriba):
#
# 10. El Articulo 309 de este Codigo termina con una lista de incisos con
#     letra (a, b, c). El inciso a) SI cierra con punto final
#     ("...violencia fisica o moral."), pero los incisos b) y c) NO tienen
#     punto final -- typo real del propio PDF fuente, inconsistente dentro
#     de la misma lista. Como la ULTIMA linea de contenido del Articulo 309
#     es el inciso c) sin punto final, _is_midsentence_line (disenada para
#     detectar citas de otro articulo cortadas a mitad de oracion, ver
#     LEY_TORTURA_EXTRACTO_REAL arriba) trataba el Articulo 310 real que
#     viene justo despues como continuacion del 309 en vez de un encabezado
#     nuevo, fusionando el Articulo 310 completo dentro del contenido del
#     309 -- un articulo entero (con su propia sancion penal) desaparecido
#     del chunking.
CODIGO_PENAL_EXTRACTO_REAL = (
    "Art\u00edculo 309.- Se equipara al despojo y se sancionar\u00e1 con prisi\u00f3n de cuatro a ocho a\u00f1os\n"
    "de prisi\u00f3n y multa de doscientos a quinientos d\u00edas de salario:\n"
    "I.- Al que ocupe temporalmente un inmueble ajeno, lo aproveche para s\u00ed o para otro, o\n"
    "ejerza sobre el mismo acto de dominio.\n"
    "La pena se aumentar\u00e1 hasta en una mitad cuando concurra alguna de las siguientes\n"
    "circunstancias:\n"
    "a) Que el delito se cometa con violencia f\u00edsica o moral.\n"
    "b) Que sea cometido por dos o m\u00e1s personas\n"
    "c) Que sea cometido por un servidor p\u00fablico o exservidor p\u00fablico\n"
    "Art\u00edculo 310.- Se impondr\u00e1n de tres meses a dos a\u00f1os de prisi\u00f3n y de diez a cien d\u00edas de\n"
    "multa, al que altere t\u00e9rminos o linderos o cualquier clase de se\u00f1al destinada a fijar los l\u00edmites\n"
    "de predios contiguos, lo anterior, independientemente de las penas que correspondan por\n"
    "la comisi\u00f3n del delito de despojo o cualquier otro il\u00edcito penal.\n"
    "Art\u00edculo 311.- Las sanciones previstas en este cap\u00edtulo se impondr\u00e1n, aunque el derecho\n"
)


def test_real_document_unpunctuated_enum_item_does_not_swallow_next_articulo():
    chunks = chunk_legal_text(
        CODIGO_PENAL_EXTRACTO_REAL,
        document_nombre="Codigo Penal para el Estado de Chiapas",
    )

    assert [c.articulo_numero for c in chunks] == ["309", "310", "311"]

    articulo_309 = next(c for c in chunks if c.articulo_numero == "309")
    assert "Art\u00edculo 310" not in articulo_309.content

    articulo_310 = next(c for c in chunks if c.articulo_numero == "310")
    assert "altere t\u00e9rminos o linderos" in articulo_310.content


# Extracto real (verbatim) del Codigo de Procedimientos Civiles para el
# Estado de Chiapas (fuente: Congreso del Estado). Bug real: TODO encabezado
# de Titulo/Capitulo/Seccion de este documento cierra con un punto final
# pegado al ultimo ordinal ("TITULO PRIMERO.", "CAPITULO I."), sin espacio de
# por medio. Antes del fix, ningun encabezado de este documento matcheaba en
# absoluto (ni el camino estricto ni el flexible de _match_header, que exige
# que cada palabra ordinal este seguida de un espacio o fin de linea, nunca
# de un punto), asi que la jerarquia Titulo/Capitulo se quedaba en None
# durante todo el documento -- el chunker caia de facto en un split ciego
# por articulo sin jerarquia. Ver docstring completo del hallazgo en
# ingestion/load_codigo_procedimientos_civiles.py.
CODIGO_PROC_CIVILES_EXTRACTO_REAL = (
    "TITULO PRIMERO.\n"
    "DE LAS ACCIONES Y EXCEPCIONES.\n"
    "CAPITULO I.\n"
    "DE LAS ACCIONES.\n"
    "ART. 1.- LAS DISPOSICIONES DE ESTE CODIGO SON DE ORDEN PUBLICO.\n"
    "TITULO SEGUNDO.\n"
    "DE LA COMPETENCIA.\n"
    "CAPITULO I.\n"
    "REGLAS GENERALES.\n"
    "ART. 2.- ES JUEZ COMPETENTE EL DEL LUGAR QUE EL DEMANDADO HAYA DESIGNADO.\n"
)


def test_real_document_trailing_period_after_titulo_capitulo_ordinal_is_detected():
    chunks = chunk_legal_text(
        CODIGO_PROC_CIVILES_EXTRACTO_REAL,
        document_nombre="Codigo de Procedimientos Civiles para el Estado de Chiapas",
    )

    assert [c.articulo_numero for c in chunks] == ["1", "2"]

    articulo_1 = next(c for c in chunks if c.articulo_numero == "1")
    assert articulo_1.titulo == "PRIMERO"
    assert articulo_1.capitulo == "I"

    articulo_2 = next(c for c in chunks if c.articulo_numero == "2")
    assert articulo_2.titulo == "SEGUNDO"
    assert articulo_2.capitulo == "I"

    # El punto final no debe quedar pegado a la metadata ni a la cita
    # embebida (ver label.rstrip(".") en _match_header).
    assert "PRIMERO." not in articulo_1.to_embedding_text()


# Extracto real (verbatim) de la Ley de Fraccionamientos y Conjuntos
# Habitacionales para el Estado y los Municipios de Chiapas (fuente:
# Congreso del Estado). Bug real: el encabezado real de la seccion de
# Transitorios en este PDF es "TRANSITORIOS." con punto final pegado (misma
# convencion tipografica que el Codigo de Procedimientos Civiles, ver arriba).
# Antes del fix, TRANSITORIO_RE no aceptaba ese punto, la seccion de
# transitorios nunca se reconocia como limite, y todo su contenido (incluidas
# las firmas y fecha del decreto al final del archivo) se fusionaba
# silenciosamente como contenido del ultimo articulo real. Ver docstring
# completo del hallazgo en ingestion/load_ley_fraccionamientos.py.
LEY_FRACCIONAMIENTOS_EXTRACTO_REAL = (
    "ART\u00cdCULO 141.- LOS ACUERDOS O RESOLUCIONES ADMINISTRATIVAS DICTADAS POR EL\n"
    "MUNICIPIO PODR\u00c1N SER IMPUGNADOS MEDIANTE EL RECURSO CORRESPONDIENTE.\n"
    "TRANSITORIOS.\n"
    "ART\u00cdCULO PRIMERO.- EL PRESENTE DECRETO ENTRAR\u00c1 EN VIGOR AL D\u00cdA SIGUIENTE\n"
    "DE SU PUBLICACI\u00d3N.\n"
    "DADO EN EL SAL\u00d3N DE SESIONES DEL HONORABLE CONGRESO DEL ESTADO.\n"
)


def test_real_document_transitorios_with_trailing_period_does_not_leak_into_last_articulo():
    chunks = chunk_legal_text(
        LEY_FRACCIONAMIENTOS_EXTRACTO_REAL,
        document_nombre=(
            "Ley de Fraccionamientos y Conjuntos Habitacionales para el "
            "Estado y los Municipios de Chiapas"
        ),
    )

    assert [c.articulo_numero for c in chunks] == ["141"]

    articulo_141 = chunks[0]
    assert "TRANSITORIOS" not in articulo_141.content
    assert "SAL\u00d3N DE SESIONES" not in articulo_141.content
    assert articulo_141.content.strip().endswith(
        "IMPUGNADOS MEDIANTE EL RECURSO CORRESPONDIENTE."
    )
