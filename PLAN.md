# PLAN.md — Roadmap de ejecucion LexChiapas

Plan de trabajo por fase para continuar el proyecto. Pensado para que
cualquier sesion/agente de Claude Code pueda retomarlo sin contexto previo:
lee esto + `CLAUDE.md` + el brief (`LexChiapas_Chatbot_Legal_RAG_BRIEF.md`) y
ya sabe donde esta parado el proyecto y que sigue.

**Convencion de este documento:** cada tarea indica `[Subagente: nombre]`
cuando conviene invocar uno de `.claude/agents/` (`data-extraction`,
`database`, `security`, `logic`, `bugs`) en vez de trabajar la tarea a mano.
Marca cada casilla al completarla y actualiza la seccion "Estado actual" al
final de cada fase.

**Documentos fuente aparte** (fuera de este archivo, leer directo cuando la
fase los referencia): `LexChiapas_Guardrails.md` (detalle de Fase 2.5),
`LexChiapas_Memoria_Conversacional.md` (detalle de Fase 2.6),
`LexChiapas_Evolucion_RAG_Progresiva.md` (detalle tecnico de Fases 6-8),
`LexChiapas_Formato_y_Mejoras_Futuras.md` (detalle de Fase 3.5 y de las
mejoras RAG condicionadas dentro de Fase 6), `LexChiapas_Reranker_y_Cache_
Semantico.md` y `LexChiapas_Refuerzos_Pendientes.md` (detalle de Fase 3.7),
y `WEB_FRONTEND_PLAN.md` (iniciativa paralela del frontend web, la lleva
otra sesion — ver el puntero al final de este documento, no duplicar su
contenido aqui).

---

## Fase 0 — Andamiaje (COMPLETADA)

Ya existe el scaffold completo de `lexchiapas/` (FastAPI, modelos SQLAlchemy
de las 6 tablas, pipeline RAG con stubs funcionales, BaseBot/TelegramBot,
Celery, scrapers/parsers, `ai_config.json`, `.env.example`). Es codigo que
**compila y tiene un test unitario pasando** (`tests/test_chunker.py`), pero
NO ha corrido nunca contra una base de datos real, una API key real, ni un
documento legal real. Todo lo de aqui en adelante es validar y completar ese
andamiaje con datos y servicios reales.

- [x] Estructura de carpetas `lexchiapas/` segun brief seccion 8
- [x] Modelos SQLAlchemy: `documents`, `chunks`, `conversations`, `messages`, `feedback`, `ingestion_logs`
- [x] `app/rag/chunker.py` con deteccion Titulo/Capitulo/Seccion/Articulo + test unitario
- [x] `app/rag/retriever.py` (dense pgvector + sparse BM25 + hybrid merge), `reranker.py` (placeholder de heuristica), `generator.py` (prompt con grounding + disclaimer), `rag_pipeline.py`
- [x] `app/llm/providers.py` + `router.py` (fallback multi-modelo desde `ai_config.json`)
- [x] `app/bots/base_bot.py` + `telegram_bot.py` (persistencia de conversacion/mensajes)
- [x] `app/api/`: health, telegram_webhook (con verificacion de secret token), whatsapp_webhook (stub), admin (con API key)
- [x] `app/workers/celery_app.py` + tareas de ingesta/actualizacion (stubs)
- [x] `ingestion/scrapers/` (Congreso, Consejeria) y `ingestion/parsers/` (PDF, HTML)

---

## Fase 1 — Ingesta + RAG core (consola, sin bot)

Objetivo del brief: pipeline RAG funcionando por consola con citas.

- [x] Instalar PostgreSQL local + extension `pgvector` (`CREATE EXTENSION vector;`)
      `[Subagente: database]` — hecho: se compilo pgvector 0.8.4 desde codigo
      fuente con MSVC 2022 + nmake (necesito PG18, pgvector 0.8.0 no compila
      contra PG18 por un cambio de firma en `vacuum_delay_point`; 0.8.4 si).
      Ver "Entorno real" al final de este documento para la conexion.
- [x] Crear las tablas reales (`Base.metadata.create_all`) y confirmar
      que la columna `chunks.embedding` tiene la dimension correcta para el
      modelo de embeddings elegido `[Subagente: database]` — hecho: las 6
      tablas existen en la DB real, `chunks.embedding` es `vector(1024)`
      (coincide con `ai_config.json` embeddings.dimension). Tambien se
      instalaron las dependencias de `requirements.txt` en el entorno conda
      del proyecto (`lexchiapas-chatbot-legal-rag-brief`).
- [x] Conseguir API key de NVIDIA NIM (`nvapi-...`) — el usuario la genero y
      ya esta en `lexchiapas/.env`. Se verifico contra `/v1/models` (121
      modelos disponibles) y con llamadas reales. **Los slugs de
      `ai_config.json` eran ilustrativos y estaban MAL** — se corrigieron:
      - LLM fallback real: `minimaxai/minimax-m3`, `deepseek-ai/deepseek-v4-pro`,
        `z-ai/glm-5.2` (los anteriores `minimax-m2.7`/`deepseek-3.2`/
        `zhipuai/glm-5.1` no existen o dan 404; `minimax-m2.7` si existe pero
        es un modelo "thinking" que gasta tokens en `reasoning_content` antes
        de la respuesta final, por eso se prefirio `minimax-m3`).
      - Embeddings: `nvidia/nv-embedqa-e5-v5` si era correcto, dimension 1024
        confirmada contra la API real (coincide con la columna `vector(1024)`).
      - Si alguno de estos empieza a fallar en el futuro, volver a listar
        `GET /v1/models` antes de asumir que el slug sigue existiendo — el
        catalogo cambia.
- [x] Elegir 1 area de derecho acotada para validar (ej. una sola ley corta)
      y descargar su PDF/HTML manualmente para la primera prueba
      `[Subagente: data-extraction]` — hecho: se eligio la **Ley de Amnistia
      del Estado de Chiapas** (Periodico Oficial No. 296, Decreto 129, 4 de
      febrero de 1994), 3 paginas, 7 articulos + transitorios. Es la ley mas
      corta encontrada en el listado real de Consejeria Juridica (139 leyes
      listadas en total), ideal para validar el chunker a mano articulo por
      articulo. PDF real guardado en `lexchiapas/data/raw/ley_de_amnistia.pdf`
      (209395 bytes) y texto extraido en
      `lexchiapas/data/processed/ley_de_amnistia.txt`. Descargada de
      `https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/Leyes/pdf/LEY%20DE%20AMNISTIA.pdf`.
      Lista para que el siguiente paso (`embed_and_store_chunks` con la API
      de NVIDIA, ya disponible) la cargue de verdad en la DB en vez del texto
      sintetico usado hasta ahora.
- [x] Verificar los selectores CSS de `congreso_scraper.py` /
      `consejeria_scraper.py` contra el HTML real (hoy son genericos,
      `a[href$='.pdf']`, sin confirmar) `[Subagente: data-extraction]`
      — resultado dispar entre los dos:
      - **`congreso_scraper.py` (Congreso del Estado): NO funciona.** El
        HTML real que devuelve `requests.get` para la pagina de
        `legislacion-vigente` no trae ningun link a PDF: el listado real de
        leyes se carga por JavaScript (probable llamada AJAX) despues de la
        carga inicial, asi que nunca aparece en el HTML estatico que
        `requests` obtiene. No es un problema del selector en si
        (`a[href$='.pdf']` es correcto en principio, simplemente no hay
        nada que matchear). Arreglarlo de verdad requeriria un navegador
        headless (Selenium/Playwright), que no esta en `requirements.txt` —
        se dejo documentado en el codigo en vez de meter una dependencia
        nueva sin decidirlo explicitamente. Para esta tarea se uso el
        scraper de Consejeria Juridica en su lugar.
      - **`consejeria_scraper.py` (Consejeria Juridica): tenia 2 bugs
        reales, ya arreglados.** (1) El `BASE_URL` original
        (`consejeriajuridica.chiapas.gob.mx/MarcoJuridico`) esta mal/roto:
        redirige a la pagina de un ayuntamiento municipal (Acala) que no
        tiene nada que ver con leyes estatales. El listado real vive en
        `https://institutodelaconsejeriajuridica.chiapas.gob.mx/Marco_Juridico/Leyes/`
        (dominio distinto, con "institutodela" al inicio). (2) Aun con el
        selector `a[href$='.pdf']` correcto (140 matches contra el HTML
        real), `link.get_text()` daba vacio siempre porque cada link es
        solo un `<img>` icono sin texto; el nombre real de la ley esta en
        la celda `<td>` anterior de la misma fila `<tr id="fila_tabla">`,
        no en el propio link. Se reescribio `list_available_laws()` para
        recorrer por fila en vez de por link suelto. Tambien se encontro
        que los `href` reales apuntan al dominio VIEJO
        (`consejeriajuridica.chiapas.gob.mx`, sin el prefijo
        "institutodela"), que da 404 para ese mismo path; `download_pdf()`
        ahora reintenta con el dominio que si responde si el primero da
        404. Probado end-to-end contra el sitio real: 139 leyes listadas,
        descarga de "LEY DE AMNISTIA." exitosa (209395 bytes, coincide
        byte a byte con el PDF bajado manualmente).
- [x] Correr `extract_text_from_pdf` sobre el PDF real y revisar que el texto
      salga en orden (columnas, encabezados repetidos, pies de pagina)
      `[Subagente: data-extraction]` — funciono tal cual, sin cambios en
      `pdf_parser.py`. El texto de las 3 paginas sale en orden logico
      correcto (articulos 1 a 7 en secuencia, transitorios al final, firmas
      al cierre). Unico ruido notable: pies de pagina intercalados
      (`17/10/2022 02:20 p.m. 1`, `(F. DE E., P.O. 4 DE FEBRERO DE 1994)`)
      que quedan como lineas sueltas dentro del texto extraido — no rompen
      el chunking porque no matchean ningun regex de limite y quedan como
      contenido dentro del articulo activo (aceptable para este documento
      corto; en un documento mas largo convendria filtrarlos
      explicitamente, no se hizo aqui por estar fuera de alcance de esta
      tarea puntual).
- [x] Correr `chunk_legal_text` sobre ese texto real y comparar chunk por
      chunk contra el documento fuente — el regex de `ARTICULO_RE` asume
      `"ARTICULO 45.- "`; confirmar que coincide con el formato real (puede
      variar: `"Articulo 45o.-"`, `"ARTÍCULO 45. "`, etc.) y ajustar si hace
      falta `[Subagente: data-extraction]` — **el regex real SI necesito
      ajuste; se encontraron 2 bugs reales, ambos arreglados:**
      1. El PDF real usa `"ARTICULO 1º.- "` (un indicador ordinal despues
         del numero). Pero `pdfplumber` extrae ese indicador ordinal en
         superindice de la fuente del PDF como el caracter DEGREE SIGN
         (U+00B0), no como la letra "o" ni como una tilde/acento que
         `_strip_accents` (NFKD) normalice — DEGREE SIGN no tiene
         descomposicion NFKD, asi que sobrevive intacto. El `ARTICULO_RE`
         original (`\d+[A-Z]*\s*[.\-]`) exigia que justo despues del numero
         viniera una letra mayuscula o el separador `.`/`-`; con el DEGREE
         SIGN en medio, el regex no matcheaba y el articulo completo se
         perdia (no un chunk mal atribuido, sino un articulo entero que
         desaparecia sin generar ningun chunk). Arreglado agregando una
         clase de caracteres opcional para el indicador ordinal entre el
         numero y el separador, y un separador final `[.\-]+` (uno o mas,
         para cubrir tanto `"45.- "` como `"45. "` sin guion). Tambien se
         agrego soporte para el prefijo abreviado `"ART."` ademas de
         `"ARTICULO"` completo (variante mencionada en el brief, no
         encontrada en este documento en particular pero facil de cubrir
         sin romper nada existente).
      2. **Bug adicional encontrado (fuera del checklist original pero
         real):** la seccion `"T R A N S I T O R I O"` (letras espaciadas,
         formato comun en PDFs legales viejos) al final del documento no
         era reconocida por ningun regex existente. Sin un limite que la
         detectara, su contenido (`PRIMERO.-`, `SEGUNDO.-`, firmas, fecha de
         decreto) quedaba pegado como si fuera parte del contenido del
         ultimo articulo real (Articulo 7) — exactamente el tipo de "chunk
         mal atribuido a un articulo que no le corresponde" que es la regla
         de oro a evitar en este proyecto. Se agrego `TRANSITORIO_RE`, que
         actua como limite igual que Titulo/Capitulo/Seccion (hace
         `flush()` y resetea el articulo activo) pero no genera su propio
         chunk. Verificado que el contenido del Articulo 7 ya no incluye
         "TRANSITORIO" ni "PRIMERO" despues del fix.
      - Se intento tambien validar `TITULO_RE`/`CAPITULO_RE`/`SECCION_RE`
        contra este documento, pero la Ley de Amnistia no tiene esa
        jerarquia (va directo a articulos sin Titulo/Capitulo/Seccion), asi
        que no hubo caso real para probarlos en esta pasada — siguen
        validados solo por el test sintetico existente. Pendiente para
        cuando se cargue una ley con jerarquia completa (ej. un Codigo).
      - `pytest tests/test_chunker.py` corre **6/6 en verde**: los 4 tests
        originales sobre el `SAMPLE_LAW` sintetico siguen pasando sin
        cambios, mas 2 tests nuevos con un extracto REAL y verbatim de la
        Ley de Amnistia (`LEY_AMNISTIA_EXTRACTO_REAL` en
        `tests/test_chunker.py`), cubriendo especificamente el bug del
        DEGREE SIGN y el bug de TRANSITORIO como regresion. El caracter
        real se guarda como escape `°` (no como tilde/simbolo literal)
        para mantener `tests/test_chunker.py` en ASCII puro, consistente
        con la convencion del proyecto.
- [x] Cargar un documento end-to-end: `embed_and_store_chunks` contra la base
      real `[Subagente: database]` + `[Subagente: data-extraction]` — **la
      Ley de Amnistia real (7 articulos) ya esta cargada en la tabla
      `documents`/`chunks` de la base `lexchiapas`**, con embeddings reales
      de NVIDIA NIM (`document.id=4` al momento de escribir esto). Ya no es
      dato sintetico, se quedo en la DB como la primera ley real del
      proyecto (a diferencia de los intentos con `SAMPLE_LAW`, que se
      insertaron y borraron durante las pruebas).
- [x] Probar `answer_question()` por consola con preguntas reales sobre la
      Ley de Amnistia `[Subagente: logic]` — probadas 4 preguntas (3
      relevantes + 1 fuera de dominio). Las 3 relevantes citan el articulo
      correcto (1, 4 y 7 respectivamente) con `grounded: True`; la pregunta
      fuera de dominio ("horario del registro civil") devuelve
      `grounded: False` y el mensaje estandar de "no encontre informacion"
      **sin llamar al LLM**. Ver el bug de calibracion de threshold abajo,
      que se encontro y arreglo precisamente en esta prueba.
- [x] Revisar que el pipeline realmente usa `psycopg` v3 end-to-end sin
      fallar por versiones `[Subagente: bugs]` — funciono una vez arreglados
      los bugs de abajo.

**Bugs reales encontrados y arreglados al probar con la API/DB real:**

1. `app/llm/providers.py` `embed_text()`: NV-Embed es un modelo asimetrico y
   la API de NVIDIA rechaza la llamada (400 `'input_type' parameter is
   required for asymmetric models'`) si no se manda `input_type` ("query" o
   "passage") via `extra_body`. Se agrego el parametro con default `"query"`;
   `app/rag/embeddings.py` ahora pasa `input_type="passage"` al embeber
   chunks para ingesta. Importa no solo para que la llamada no falle, sino
   para la calidad del retrieval (embeddings asimetricos: query y passage se
   codifican distinto a proposito).
2. `app/rag/retriever.py` `dense_search()`: pasar una lista de Python como
   parametro crudo a `psycopg` la manda como `double precision[]`, y pgvector
   no tiene el operador `<=>` para `vector <=> double precision[]`
   (`UndefinedFunction`). Se agrego `_to_vector_literal()` para formatear el
   embedding como literal de texto pgvector, y se caste explicitamente con
   `CAST(:query_vector AS vector)` en el SQL — **no usar `:query_vector::vector`**,
   SQLAlchemy interpreta el `::` pegado al bind param como ambiguo y deja de
   bindearlo silenciosamente (el placeholder se pasa literal al driver, que
   truena con un error de sintaxis distinto y confuso).
3. **Bug de diseño real en el gate anti-alucinacion** (encontrado probando
   una pregunta fuera de dominio): `sparse_search()` (BM25) normaliza su
   mejor resultado a similarity=1.0 SIEMPRE, sin importar que tan irrelevante
   sea el match, y no tiene ningun threshold absoluto (solo exige
   `score > 0`). Como `hybrid_search()` mezclaba dense+sparse y
   `rag_pipeline.answer_question()` calculaba `grounded = bool(top_chunks)`,
   una pregunta totalmente fuera de dominio podia colar un chunk irrelevante
   via sparse con "similarity 1.0" y marcarse como `grounded: True` (el LLM
   igual respondio bien en texto porque es un buen modelo, pero el campo
   `grounded` del sistema mentia — cualquier logging/monitoreo que confiara
   en ese campo se hubiera enganado). Arreglado: `RetrievedChunk` ahora tiene
   `passed_threshold: bool`, que `dense_search()` marca `True` (ya viene
   filtrado por el `WHERE` del SQL) y que sparse-only NUNCA marca. En
   `rag_pipeline.py`, `grounded = any(c.passed_threshold for c in top_chunks)`,
   y si nada paso el threshold real, **no se llama al LLM en absoluto** (se
   devuelve el mensaje de "no encontre informacion" directo).
4. **`similarity_threshold` de `ai_config.json` estaba mal calibrado: 0.75
   dejaba pasar CERO preguntas relevantes.** Al arreglar el bug #3 arriba, la
   pregunta relevante "Los menores de edad estan incluidos en la amnistia?"
   (que antes SI se contestaba bien, pero solo gracias al bug del gate)
   empezo a devolver `grounded: False` — es decir, el gate correcto revelo
   que dense_search nunca superaba 0.75 ni para matches correctos. Se midio
   la similitud coseno real de `nvidia/nv-embedqa-e5-v5` contra la Ley de
   Amnistia: preguntas relevantes caen en **0.56–0.64**, preguntas
   claramente irrelevantes ("capital de Francia", "receta de pozol") caen en
   **0.20–0.44**. Hay separacion clara entre ambos grupos. Se recalibro
   `similarity_threshold` a **0.5** (antes 0.75) con esta evidencia. Esto es
   una muestra chica (una sola ley, 6 preguntas) — Fase 2 deberia repetir
   esta medicion con mas leyes y mas preguntas antes de confiar en 0.5 como
   valor final. Si se cambia el modelo de embeddings en el futuro, hay que
   re-medir esto: el rango de similitud "normal" es especifico del modelo.

**Entregable: CUMPLIDO.** Pregunta por consola -> respuesta con cita, sobre
una ley real (Ley de Amnistia) cargada en Postgres, con gate anti-alucinacion
verificado tanto en el caso positivo como negativo.

---

## Fase 2 — Hybrid search + calidad

Objetivo del brief: mejorar recuperacion, evitar alucinacion.

- [x] Cargar 3-5 leyes mas (siguiendo la estrategia de "un area acotada
      primero") para tener suficiente corpus como para que BM25 y el
      threshold tengan sentido `[Subagente: data-extraction]` — **hecho: 3
      leyes reales nuevas cargadas con embeddings reales**, corpus total
      ahora en 4 documentos:
      - **Ley de Bibliotecas para el Estado de Chiapas** (area `cultural`),
        43 chunks (algunos articulos largos se dividieron en varias piezas,
        ver bug de limite de tokens abajo). `document.id=7`.
      - **Ley Estatal para Prevenir y Sancionar la Tortura del Estado de
        Chiapas** (area `derechos_humanos`), 14 chunks. `document.id=8`.
      - **Ley de Adopcion para el Estado de Chiapas** (area `familiar`),
        45 chunks. `document.id=9`.
      - Fuente: `consejeria_scraper.py` (ya arreglado en Fase 1), PDFs reales
        guardados en `lexchiapas/data/raw/` y texto en
        `lexchiapas/data/processed/` (`ley_biblioteca.*`, `ley_tortura.*`,
        `ley_adopcion.*`).
      - Se probaron 6 preguntas especificas (2 por ley) mas 1 pregunta de
        control sobre la Ley de Amnistia (Fase 1) y 1 fuera de dominio.
        Resultado final (despues de los 2 bugs de abajo): **5/6 preguntas
        especificas con `grounded: True` y cita al articulo correcto**;
        la pregunta de control y la de fuera de dominio siguen funcionando
        como se espera. La 1 pregunta que quedo en `grounded: False`
        ("Que sanciones existen para el delito de tortura?") es un caso
        LEGITIMO de threshold limite, no un bug — ver nota de threshold
        abajo.
- [x] Afinar `similarity_threshold` en `ai_config.json` con mas leyes y mas
      preguntas de prueba reales `[Subagente: logic]` — **se recopilo
      evidencia pero NO se cambio el valor todavia** (sigue en 0.5). Dato
      nuevo: la pregunta "Que sanciones existen para el delito de tortura?"
      tiene como mejor similitud dense real **0.4525** contra el articulo
      correcto de la Ley de Tortura (todos los top-8 candidatos SIN
      threshold son de esa misma ley, la recuperacion es correcta, solo que
      ningun score cruza 0.5). Esto sugiere que 0.5 esta en el limite
      superior de lo tolerable y podria estar generando falsos negativos en
      preguntas legitimas con corpus mas grande. Pendiente: acumular mas
      preguntas de prueba (idealmente 15-20) antes de mover el valor de
      nuevo — un solo data point no es suficiente para recalibrar con
      confianza.
- [ ] Reemplazar el reranker placeholder (`app/rag/reranker.py`, hoy
      solapamiento de palabras) por algo mas serio: un cross-encoder o el
      endpoint de reranking de NVIDIA NIM si esta disponible
      `[Subagente: logic]` — sigue pendiente, pero ya no tiene el bug de
      ranking descrito abajo (arreglado, no reemplazado del todo).
- [ ] Ajustar pesos `dense_weight`/`sparse_weight` de `hybrid_search` con
      casos donde BM25 deberia ganar (terminologia legal exacta) vs donde
      dense deberia ganar (parafraseo) `[Subagente: logic]`
- [x] Escribir un set de preguntas de regresion (con la respuesta esperada:
      articulo correcto o "no encontrado") y automatizarlas como test
      `[Subagente: logic]` + revisar con `[Subagente: bugs]` si algo falla
      — **hecho: `tests/test_rag_regression.py`, 24 preguntas reales contra
      el corpus activo completo (~19 documentos: penal, cultural,
      derechos_humanos, familiar, transito, fiscal, salud, laboral,
      administrativo, civil -- incluyendo los 4 Libros del Codigo Civil --
      y ambiental), cada articulo/ley esperado verificado a mano contra la
      tabla `chunks` real antes de escribir la pregunta (no inventado). Cada
      test llama al pipeline real `answer_question()` sin mocks (DB real +
      NVIDIA NIM real). Corrida completa (`pytest tests/test_rag_regression.py
      -v -s`, 2086.72s = 34m47s, un solo proceso, 5 modelos de fallback con
      timeout de 60s cada uno explican la duracion): **17 passed, 2 xfailed
      (limitaciones ya documentadas arriba en esta misma seccion —
      tortura-sanciones bajo threshold y Art. 1576 de Sucesiones fuera del
      top-K — confirmadas vigentes con el corpus mas grande), 5 failed**
      (hallazgos NUEVOS, documentados en el docstring de cada test, no
      ocultos): 2 son solapamiento real entre leyes que compiten por el
      top-K (Codigo Civil vs Ley de Adopcion; un articulo de definiciones
      largo del Codigo de Atencion a la Familia que diluye la senal
      semantica de "adulto mayor" entre otras 35 fracciones), y 3 son casos
      donde lenguaje legal generico/boilerplate de OTRAS leyes cruza
      similarity_threshold=0.5 sin responder la pregunta real (proteccion
      al consumidor, Codigo Penal, proteccion animal) — revelando que
      `grounded=True` mide solo si algun chunk cruzo el umbral, no si el
      LLM realmente pudo responder; ningun caso fue alucinacion real
      (articulo inventado), todos citaron articulos reales del corpus, solo
      no siempre el mas pertinente. Ver docstrings de
      `tests/test_rag_regression.py` para el detalle completo por caso.
- [ ] Auditoria de grounding: para cada respuesta generada, confirmar que
      cada afirmacion especifica es trazable a un chunk (no inventada)
      `[Subagente: logic]` — nota: ya se arreglo en Fase 1 el bug de que
      `grounded` podia dar `True` por un match de sparse/BM25 sin threshold
      real (ver "Bugs reales" de Fase 1, item 3); este item es sobre el
      contenido de la respuesta en si, no sobre el flag `grounded`.
- [ ] Revisar seguridad de esta capa: que el contenido scrapeado no pueda
      romper la estructura del prompt (prompt injection via texto legal
      malformado) `[Subagente: security]`

**Bugs reales encontrados y arreglados al cargar mas leyes (con 1 sola ley en
el corpus, en Fase 1, estos bugs eran invisibles):**

1. **`app/rag/embeddings.py`: limite de tokens del modelo de embeddings.**
   El Articulo 15 de la Ley de Bibliotecas tiene 4157 caracteres de
   contenido; la API de NVIDIA (`nvidia/nv-embedqa-e5-v5`) rechazo la llamada
   (400 `"Input length ... exceeds maximum allowed token size 512"`). La
   unidad de chunk natural sigue siendo el articulo completo (no se cambio
   `app/rag/chunker.py`), pero un articulo real puede exceder el limite de
   tokens del modelo. Se agrego `_split_content_for_embedding()`, que
   sub-divide el contenido en piezas mas chicas (respetando limites de linea
   y de oracion, nunca cortando a mitad de palabra) que comparten el mismo
   `articulo_numero`/`titulo`/`capitulo`/`seccion` (misma cita al usuario,
   aunque el contenido embebido de cada `Chunk` en la DB sea solo una parte).
   Un primer intento con 1500 caracteres SIGUIO fallando (el texto legal en
   espanol resulto mas denso en tokens de lo asumido, ~2.6 caracteres/token
   en vez de 3-4); se bajo a `MAX_EMBEDDING_CHARS = 900`, que funciono para
   las 3 leyes.
2. **`app/rag/chunker.py`: cita a otro articulo a mitad de oracion
   confundida con un encabezado real.** La Ley de Tortura tiene texto como
   `"...SE ESTARA A LO ESTABLECIDO EN LA PARTE FINAL DEL\nARTICULO 4o. DE
   ESTE ORDENAMIENTO."`, y pdfplumber corta esa cita justo al inicio de una
   linea de PDF — `ARTICULO_RE` la matcheaba como si fuera un articulo nuevo,
   truncando el articulo activo a la mitad y generando un chunk fantasma
   (exactamente el tipo de "chunk mal atribuido" que es la regla de oro a
   evitar). Se agrego una heuristica: un match de `ARTICULO_RE` solo cuenta
   como limite real de articulo si la ultima linea de contenido no vacia del
   articulo activo termina en `.`, `:`, `;` o `)` (cierre de idea/oracion);
   si no, se trata como texto normal (parte del articulo activo). El `)`
   se acepta porque esta misma ley cierra articulos reformados con
   anotaciones legislativas entre parentesis antes del siguiente `ARTICULO`
   real. Test de regresion:
   `test_real_document_midsentence_article_reference_does_not_split_chunk`.
3. **`app/rag/reranker.py`: el mas importante, un bug de diseno en el
   ranking que solo se volvio visible con >1 ley en el corpus.**
   `RetrievedChunk.similarity` NO es una sola escala comparable: para chunks
   que vienen de `dense_search()` es cosine similarity real (0-1 absoluto);
   para chunks que vienen SOLO de `sparse_search()` (BM25) es el score
   normalizado al MAXIMO POR CONSULTA (siempre hay un chunk con
   `similarity=1.0`, sin importar que tan irrelevante sea el mejor match de
   esa consulta en particular — este comportamiento de BM25 ya estaba
   documentado desde Fase 1). El `rerank()` original ordenaba solo por
   `similarity + overlap_de_palabras`, asi que un chunk de una ley
   TOTALMENTE DISTINTA con `similarity=1.0` inflado por BM25 desplazaba del
   top-K a chunks genuinamente relevantes que SI habian pasado el threshold
   real de `dense_search()` — produciendo `grounded: False` (falso negativo)
   en preguntas claramente dentro de dominio. Con 1 sola ley en el corpus
   (Fase 1) esto no se manifestaba porque no habia contenido irrelevante que
   BM25 pudiera inflar. Con 4 leyes, **4 de 6 preguntas especificas
   fallaron** antes de este fix. Arreglado ordenando primero por
   `passed_threshold` (los chunks que pasaron el gate anti-alucinacion real
   nunca quedan por debajo de los que no) y solo como criterio secundario
   por `similarity + overlap`. Verificado: las mismas 6 preguntas pasaron a
   5/6 `grounded: True` (la 6ta es el caso legitimo de threshold-limite
   documentado arriba, no este bug).
4. **`app/llm/providers.py`: sin timeout en el cliente de NVIDIA NIM.** Al
   probar la pregunta sobre sanciones de tortura, la llamada de generacion
   colgo mas de 180 segundos (contra 25-35s de preguntas comparables) sin
   lanzar ninguna excepcion — como `generate_with_fallback()` solo avanza al
   siguiente modelo del `fallback_order` ante una excepcion, un cuelgue sin
   timeout bloquea el pipeline entero indefinidamente en un solo modelo, sin
   nunca intentar el fallback. Se agrego `timeout=60.0` al cliente `OpenAI()`
   en `get_nim_client()`. Al reintentar la misma pregunta con el fix, la
   llamada se resolvio en 23.5s en el primer modelo (`minimax-m3`) — el
   cuelgue original parece haber sido una respuesta lenta/atascada
   transitoria de la API, no un problema sistematico con esa pregunta en
   particular, pero el timeout protege contra que vuelva a pasar sin
   bloquear el pipeline.

**Entregable parcial cumplido:** corpus de 4 leyes reales, hybrid search
verificado sin mezclar leyes incorrectamente. Sigue pendiente: reranker real
(no placeholder), pesos dense/sparse ajustados con mas evidencia, set de
regresion automatizado, y auditoria de seguridad del prompt.

---

## Fase 2.5 — Guardrails (contencion de alcance)

Documento fuente completo: **`LexChiapas_Guardrails.md`** (raiz del repo) —
leerlo para el detalle y las citas del caso McDonald's que motiva esto.
Resumen del problema: sin limites, el bot responde cualquier cosa (clima,
codigo, recetas), gastando tokens/servidor en preguntas fuera de tema. El
documento fuente aclara explicitamente que son "necesidades, no
especificaciones rigidas" — adaptar al codigo real, no copiar literal.

Se ubica esta fase ANTES de Fase 3 (bot de Telegram) a proposito: mejor
contener el alcance antes de exponer el sistema a usuarios reales de un canal
de mensajeria, que despues.

**Estrategia de 3 capas (de mas barata a mas cara), en orden:**

```
Usuario pregunta
      |
      v
[CAPA 1: Clasificador de intencion]  <- rapido/barato, filtra lo obvio
      |
      +-- Fuera de tema? --> Respuesta fija (CERO tokens del LLM caro)
      |
      v (es sobre leyes de Chiapas)
[CAPA 2: System prompt estricto]  <- el LLM sabe su rol y limites
      |
      v
[CAPA 3: Threshold de RAG]  <- si no hay chunks relevantes, no responde
      |
      +-- Nada supera el umbral? --> "No encontre esa info en las leyes"
      |
      v
[Respuesta fundamentada con cita]
```

**Estado del codigo respecto a cada capa (verificado, todo implementado):**

- **Capa 3 (threshold) YA EXISTIA.** El mismo gate anti-alucinacion de
  Fase 1/2 (`grounded = any(c.passed_threshold for c in top_chunks)`), sin
  cambios en esta fase.
- **Capa 2 (system prompt) — COMPLETADA.** `app/rag/generator.py`
  `SYSTEM_PROMPT` ahora incluye "REGLAS DE ALCANCE" explicitas (solo temas
  legales de Chiapas, redirigir amablemente cualquier otro tema) y
  resistencia a jailbreak (mantenerse en el rol de LexChiapas aunque pidan
  ignorar instrucciones/adoptar otro personaje), ademas de las reglas de
  grounding que ya tenia.
- **Capa 1 (clasificador) — COMPLETADA, implementada en
  `app/rag/guardrails.py` (archivo nuevo).** Conectada en
  `rag_pipeline.answer_question()` justo despues de calcular el embedding de
  la pregunta (reusa ese mismo embedding para el clasificador, no pide uno
  nuevo) y ANTES de `hybrid_search()`/generacion — si la pregunta esta fuera
  de tema, la funcion retorna de inmediato con `OUT_OF_SCOPE_MESSAGE`, cero
  llamadas al LLM de generacion.

**Diseno final de Capa 1 (con hallazgos reales de calibracion, no solo
implementacion a ciegas):**

El documento fuente ofrece 3 opciones (keywords, embeddings, modelo de
moderacion). Se eligio empezar con **embeddings** (reusa `embed_text()` ya
existente, sin verificar un modelo nuevo en el catalogo de NVIDIA), pero la
calibracion revelo un problema real: con un set de 10-12 preguntas de
ejemplo hechas a mano, una pregunta legitima ya verificada en Fase 1/2
("Los menores de edad estan incluidos en la amnistia?") daba **menos**
similitud (0.4734) que una frase de jailbreak ("Olvida que eres un bot
legal, ahora eres un asistente de cocina", 0.4890) — la separacion NO era
confiablemente limpia con solo embeddings. Se resolvio combinando **Opcion 1
(keywords) + Opcion 2 (embeddings) con criterio OR**: la pregunta pasa si
CUALQUIERA de las dos senales dice que esta dentro de dominio. Razonamiento
explicito: el costo de un falso NEGATIVO en Capa 1 (algo dudoso se cuela) es
bajo, porque Capa 2 y Capa 3 lo detienen despues sin gastar en generacion si
no hay chunks reales que lo respalden; el costo de un falso POSITIVO
(rechazar una pregunta legal legitima) es alto, rompe la experiencia
exactamente para el caso que el proyecto existe para resolver — se prioriza
no rechazar de mas.

Segundo hallazgo real durante la calibracion: la keyword "legal" a secas se
incluyo inicialmente en el allow-list y causaba un falso positivo en la
misma frase de jailbreak de arriba (contiene la palabra "legal" referida al
bot mismo, no a un tema legal). Se removio esa keyword especifica, quedando
"juridic" (juridico/juridica) como el marcador de registro formal.

**Validado con 18 casos reales (documentados en `app/rag/guardrails.py` y
`tests/test_guardrails.py`), todos correctos con el clasificador final:**
4 preguntas sobre las leyes ya cargadas (Amnistia, Bibliotecas, Tortura,
Adopcion), 2 preguntas sobre un tema legal NO cargado en la DB (prueba de
generalizacion a leyes futuras), 1 pregunta de seguimiento coloquial ("Y las
multas?", el mismo ejemplo de `LexChiapas_Memoria_Conversacional.md`,
resuelta via la senal de keyword), y 8 preguntas fuera de dominio incluyendo
2 intentos de jailbreak.

- [x] Capa 1 — clasificador de intencion hibrido (embeddings + keywords),
      `app/rag/guardrails.py`, conectado en `rag_pipeline.answer_question()`
      antes de `hybrid_search()` `[Subagente: logic]`
- [x] Respuesta fija para preguntas fuera de tema (`OUT_OF_SCOPE_MESSAGE`) —
      cero llamadas al LLM de generacion confirmado end-to-end
      `[Subagente: logic]`
- [x] Capa 2 — `SYSTEM_PROMPT` actualizado con alcance + anti-jailbreak;
      `pytest tests/` y las preguntas de regresion de Fase 1/2 (Amnistia,
      Bibliotecas) siguen pasando sin cambios `[Subagente: logic]`
- [x] Logging de intentos de manipulacion — `detect_jailbreak_attempt()` +
      `logger.warning()` (modulo `lexchiapas.guardrails`), sin bloquear.
      Se eligio logging simple en vez de una tabla nueva en la DB para no
      chocar con el trabajo paralelo de otra sesion que esta agregando
      columnas a `messages` (`prompt_tokens`, `completion_tokens`,
      `found_answer`) para el dashboard de metricas de
      `WEB_FRONTEND_PLAN.md` `[Subagente: database]` + `[Subagente: logic]`
      — si mas adelante se quiere el jailbreak logging en el dashboard,
      agregar una columna/tabla es trabajo futuro, no bloqueante ahora.
- [ ] Guardrail de salida (capa opcional del documento fuente) — **NO
      implementado a proposito**, tal como decia el checklist original: las
      3 capas base ya se verificaron suficientes con los 18 casos de prueba,
      agregar esto solo si pruebas reales mas adelante muestran que hace
      falta.
- [x] Set de preguntas de prueba (18 casos: dentro de dominio, tema no
      cargado, seguimiento coloquial, fuera de tema, jailbreak) — la parte
      deterministica (keywords + deteccion de jailbreak) esta automatizada
      en `tests/test_guardrails.py` (6 tests, sin llamadas a red); la parte
      de similitud de embeddings se valido manualmente contra la API real
      (documentado arriba) y no se automatizo como pytest porque
      requeriria red/API key disponible en cualquier maquina que corra la
      suite `[Subagente: logic]` + `[Subagente: bugs]`

**Hallazgo adicional, fuera del alcance de esta fase pero relevante para
Fase 3 (bot de Telegram):** durante las pruebas de esta fase se confirmo que
NVIDIA NIM (free tier) tiene variabilidad de latencia real y significativa
— una misma pregunta que normalmente responde en 25-35s tardo **208
segundos** en una prueba (el primer modelo del fallback, `minimax-m3`,
alcanzo el timeout de 60s configurado en Fase 2 y el segundo,
`deepseek-v4-pro`, aun asi tardo mucho mas de lo tipico antes de responder
bien). El timeout de 60s por modelo (`app/llm/providers.py`) sigue
protegiendo contra un cuelgue infinito, pero una respuesta de bot que tarda
mas de 3 minutos es mala UX para un canal de mensajeria real. Revisar antes
de exponer el bot de Telegram: bajar el timeout por modelo, o avisarle al
usuario que la respuesta esta en camino si tarda mas de X segundos.

**Fallback multi-proveedor agregado (respuesta parcial al hallazgo de
arriba, 2026-07-09):** el usuario agrego API keys de OpenAI, xAI/Grok,
Gemini y Groq a `.env`. Se investigaron los 4 contra sus APIs reales antes
de asumir que servian (misma disciplina que con NVIDIA en Fase 1):
- **OpenAI y xAI/Grok: funcionan, verificados con generacion real**
  (`gpt-4o-mini` y `grok-4.20-0309-non-reasoning`). Ambos con $5 de credito
  limitado.
- **Gemini: key valida (autentica, lista 40+ modelos) pero cuota 0 en el
  tier gratis** para al menos un modelo probado (`gemini-2.0-flash-lite`);
  `gemini-flash-latest` dio 503 de sobrecarga. Necesita revisar
  billing/tier en Google Cloud Console antes de ser utilizable.
- **Groq: key vencida** (`"expired_api_key"`). Necesita generar una key
  nueva en console.groq.com.

Decision del usuario: Gemini y Groq quedan configuradas en `.env`/
`app/config.py` pero FUERA del fallback activo hasta que sean realmente
utilizables; OpenAI y xAI se agregan al fallback como ultimo recurso
(despues de los 3 modelos de NVIDIA), no como opcion primaria, para no
gastar el credito limitado salvo que NVIDIA falle por completo.

Cambios de arquitectura (antes el router solo sabia hablar con NVIDIA):
- `ai_config.json` `llm.fallback_order` paso de una lista de strings
  (nombres de modelo) a una lista de objetos `{provider, model}`; se agrego
  `llm.providers` con el `base_url` de cada proveedor.
- `app/config.py` `Settings` gano `openai_api_key`, `xai_api_key`,
  `gemini_api_key`, `groq_api_key`.
- `app/llm/providers.py` gano `get_client_for_provider(provider)` generico
  (mapea proveedor -> api_key de Settings + base_url de ai_config.json);
  `get_nim_client()` se mantiene como alias para NVIDIA especificamente,
  usado unicamente por `embed_text()` -- los embeddings siguen siendo
  SOLO NVIDIA (NV-Embed), la dimension del vector en pgvector ya esta fija
  a ese modelo desde Fase 1, no hay necesidad de multi-proveedor ahi.
- `app/llm/router.py` `generate_with_fallback()` ahora pide un cliente
  nuevo por cada entrada de `fallback_order` (antes reusaba un solo cliente
  NVIDIA para las 3 iteraciones).

Verificado con pruebas de fallover reales (no solo revisar que compile):
simulando que los 3 modelos de NVIDIA fallan, la cadena efectivamente cae a
`gpt-4o-mini` (OpenAI); simulando que OpenAI tambien falla, cae hasta
`grok-4.20-0309-non-reasoning` (xAI) como ultimo nivel. El flujo normal
(NVIDIA sano) se reverifico intacto: sigue respondiendo con
`minimaxai/minimax-m3` como antes, sin overhead nuevo cuando NVIDIA
funciona bien.

**Entregable: CUMPLIDO.** El bot rechaza preguntas fuera de tema sin gastar
tokens del LLM principal, mantiene su rol ante intentos de jailbreak, y
sigue respondiendo bien preguntas legitimas — verificado con 18 casos reales
que cubren ambos lados mas casos limite (generalizacion a temas no
cargados, seguimiento conversacional).

---

## Fase 2.6 — Memoria conversacional (persistencia de contexto)

Documento fuente completo: **`LexChiapas_Memoria_Conversacional.md`** (raiz
del repo) — leerlo para el detalle completo. Problema que resuelve: hoy el
bot responde cada mensaje sin ningun contexto de lo hablado antes en la
misma conversacion — si el usuario pregunta "y cuales son las multas?"
despues de preguntar sobre agua potable, el sistema no tiene forma de saber
que "las multas" se refiere a agua.

Se ubica ANTES de Fase 3 (bot de Telegram) a proposito, siguiendo el mismo
criterio que Fase 2.5: mejor que `rag_pipeline.answer_question()` ya soporte
contexto conversacional cuando se conecte el bot real, en vez de retrofitear
memoria despues de que el bot ya este en produccion. Se puede construir y
probar por consola (mismo patron ya usado en Fase 1/2: simular varios turnos
de conversacion con scripts, sin necesitar el bot desplegado).

**Estado del codigo respecto al gap original (verificado antes de empezar,
no asumido — el 2026-07-09 se creyo por error que esta fase ya estaba
implementada; se reviso el codigo directamente y NO era cierto, ver notas de
proceso al final de esta seccion):**

- `app/rag/rag_pipeline.py` `answer_question(db, question)` no recibia
  historial de conversacion en absoluto.
- Un refactor de otra sesion (paralelo a este trabajo) ya habia consolidado
  la persistencia de Telegram/web en `app/bots/conversation_store.py`
  `handle_turn()` — util (evita duplicar logica entre canales), pero
  segia sin leer el historial antes de llamar a `answer_question()`: se
  guardaba la memoria pero nunca se usaba, el mismo gap de siempre.
- Redis solo estaba cableado como broker/backend de Celery, nunca para
  cache de sesion de chat.

**Implementado (archivo nuevo `app/rag/memory.py` + cambios de firma):**

- `get_recent_history(db, conversation_id, limit=8)`: ventana deslizante de
  los ultimos 8 mensajes de la conversacion, en orden cronologico, formato
  `{"role": ..., "content": ...}` listo para el LLM. Primero intenta Redis
  (cache), si falla o no hay dato cae a Postgres (fuente de verdad) y
  repuebla el cache. Postgres se implemento y verifico PRIMERO, Redis se
  agrego despues como capa de performance, siguiendo el orden recomendado
  del documento fuente.
- `invalidate_history_cache(conversation_id)`: se llama despues de persistir
  cada turno nuevo (user + assistant). Sin esto, la lectura siguiente
  devolveria el cache viejo SIN el turno recien guardado — la conversacion
  "olvidaria" el ultimo intercambio cada dos turnos, peor que no tener cache
  del todo. Se invalida en vez de actualizar in-place para no arriesgar
  inconsistencias con escrituras concurrentes.
- `answer_question()` (`rag_pipeline.py`), `generate_answer()` y
  `build_prompt()` (`generator.py`) ganaron un parametro opcional
  `conversation_history: list[dict] | None`. En `build_prompt()`, el
  historial se inserta ENTRE el system prompt y la pregunta actual (los
  turnos previos van tal cual se guardaron, sin el envoltorio "Fragmentos
  legales recuperados:" que solo lleva el turno mas reciente). Verificado
  a nivel deterministico (sin llamar a la API) que la secuencia de mensajes
  sale en el orden correcto: system, user previo, assistant previo, user
  actual con contexto RAG.
- `conversation_store.py` `handle_turn()`: lee `get_recent_history()` ANTES
  de persistir la pregunta nueva (para no incluirse a si misma como
  "historial"), se lo pasa a `answer_question()`, e invalida el cache
  despues de persistir el turno completo. `telegram_bot.py` YA delegaba en
  `handle_turn()` (por el refactor de la otra sesion), asi que Telegram y
  el chat web reciben la memoria automaticamente sin tocar esos archivos —
  el item del checklist original de "conectar telegram_bot.py" ya no aplica
  tal cual estaba escrito, se resolvio via el punto compartido.

**Bug real encontrado al conectar Redis:** el `redis-server` local corriendo
en esta maquina es version **5.0.14** (verificado con `INFO server`), que no
soporta RESP3 (requiere Redis 6.0+). `redis-py` 5.x intenta negociar RESP3
por defecto (comando `HELLO 3`), que este Redis rechaza con
`"unknown command HELLO"` — sin arreglarlo, CUALQUIER operacion fallaria y
el cache caeria siempre a Postgres en silencio (funcional pero sin el
beneficio real de Redis). Se arreglo forzando `protocol=2` en el cliente
(`app/rag/memory.py` `_get_redis_client()`).

**Prueba real end-to-end (matiz importante, no un exito total sin
condiciones):** se probo una conversacion de 2 turnos sobre la Ley de
Tortura ya cargada: "Que se considera tortura...?" seguido de "Y que
sanciones tiene?" sin repetir el tema.
- El Turno 2 dio `grounded: False` en el pipeline completo — **no
  correlaciono end-to-end**. Diagnostico: Capa 1 (guardrails) paso bien
  (0.64 de similitud, via keyword "sanciones"); `dense_search` SI encontro
  los articulos correctos de la Ley de Tortura (los 7 primeros resultados
  son de esa ley), pero el score maximo fue solo 0.385 — por debajo del
  threshold de 0.5. Una pregunta de seguimiento corta y sin palabras propias
  del tema ("Y que sanciones tiene?") no genera un embedding lo bastante
  cercano a los articulos reales, **independientemente de la memoria** — la
  memoria implementada en esta fase alimenta el PROMPT de generacion, no la
  busqueda (`hybrid_search` sigue operando solo sobre la pregunta cruda,
  igual que Capa 1). Esto es exactamente la dependencia que ya se habia
  anotado en el checklist original ("la memoria alimenta el query rewriting,
  Fase 6") — no es un bug de esta fase, es el limite conocido y esperado de
  hacer memoria SIN reescritura de consulta todavia.
- Para verificar que la parte que SI le toca a esta fase funciona, se probo
  `generate_answer()` directamente con los chunks reales de Tortura (los
  mismos que `dense_search` ya encontraba, forzados a pasar el threshold
  para aislar esta prueba) + el historial de la conversacion: el LLM
  respondio correctamente citando **Articulo 3 y Articulo 10** de la Ley de
  Tortura, entendiendo sin ambiguedad que "sanciones" se referia a tortura
  — la generacion SI usa bien la memoria una vez que tiene los chunks
  correctos, sea cual sea el mecanismo (actual o futuro) que los encuentre.

- [x] Ventana deslizante desde PostgreSQL `[Subagente: logic]` + `[Subagente: database]`
- [x] Firma de `answer_question()`/`generate_answer()`/`build_prompt()`
      extendida con `conversation_history` `[Subagente: logic]`
- [x] Probado por consola con una conversacion de seguimiento real — **con
      el matiz de arriba**: la generacion usa bien la memoria, pero el
      retrieval de ESTE follow-up especifico (corto, sin vocabulario propio)
      no pasa el threshold sin ayuda de Fase 6 `[Subagente: logic]` +
      `[Subagente: bugs]`
- [x] Conectado — via el punto compartido `conversation_store.handle_turn()`,
      Telegram y web quedan cubiertos sin tocar `telegram_bot.py` directamente
- [x] Cache de sesion en Redis con invalidacion en escritura, agregado
      DESPUES de verificar la version solo-Postgres, bug de protocolo
      RESP2/RESP3 encontrado y arreglado `[Subagente: logic]`
- [x] Nota dejada explicita en el docstring de `answer_question()` para que
      Fase 6 sepa exactamente donde conectar la reescritura de consulta
- [ ] Memoria de largo plazo con embeddings — sigue OPCIONAL/futuro, no
      implementada a proposito

**Entregable: PARCIAL al momento de escribir esto — RESUELTO despues, ver
nota.** La infraestructura de memoria (Postgres + Redis, invalidacion
correcta) esta implementada y verificada, y la generacion demostrablemente
usa el historial bien cuando tiene los chunks correctos. Pero el entregable
original ("el bot correlaciona preguntas de seguimiento... verificado con al
menos un caso real") **no se cumplia todavia para preguntas de seguimiento
cortas sin vocabulario legal propio** — dependia de Fase 6 (query rewriting)
para reformular la pregunta ANTES del retrieval. Fase 2.6 dejo la interfaz
lista (parametro `conversation_history` ya fluye por todo el pipeline) para
que Fase 6 la consumiera sin rediseñar nada.

**ACTUALIZACION (2026-07-10):** Fase 6 (item 1.1, query rewriting) ya se
implemento y se verifico con el MISMO caso exacto documentado arriba
("Y que sanciones tiene?" sobre la Ley de Tortura) — ahora si correlaciona
(`grounded: True`, cita Articulo 3 y 5). El entregable completo de Fase 2.6
queda cumplido en conjunto con Fase 6 — ver el checklist de Fase 6 arriba
para el detalle de la implementacion de query rewriting.

---

## Fase 3 — Bot de Telegram

Objetivo del brief: chatbot funcional en Telegram, probable por cualquiera.

- [x] `TELEGRAM_BOT_TOKEN` real conseguido por el usuario via @BotFather
      (bot: `@LexChiapasBot`), puesto en `lexchiapas/.env`. Verificado con
      `getMe` real contra la API de Telegram antes de usarlo.
- [x] `TELEGRAM_WEBHOOK_SECRET` — **ya estaba implementado correctamente**,
      verificado leyendo `app/api/telegram_webhook.py`: compara el header
      `X-Telegram-Bot-Api-Secret-Token` contra `settings.telegram_webhook_secret`
      y responde 401 si no coincide (mecanismo oficial de Telegram). No hizo
      falta trabajo nuevo aqui, solo confirmar que el codigo ya hacia lo
      correcto. Para las pruebas en vivo se uso **modo polling**
      (`app/bots/telegram_polling.py`, nuevo) en vez de webhook, porque
      polling no requiere exponer un endpoint HTTPS publico (ngrok, etc.) —
      valido para desarrollo local; el webhook real queda listo para cuando
      se despliegue con un dominio publico.
- [x] **Probado `/start`, `/ayuda`, `/areas` y preguntas reales DESDE
      Telegram real** (no solo consola), via polling, con el usuario
      interactuando directo con `@LexChiapasBot`. Evidencia real leida de la
      tabla `messages` despues de la sesion:
      - "Que sanciones tiene la tortura en Chiapas?" -> respondida con cita
        real (Ley Estatal para Prevenir y Sancionar la Tortura, Articulo 3),
        `found_answer=True`.
      - "La capital de Francia es?" -> rechazada correctamente por
        guardrails (fuera de dominio), sin llamar al LLM generador.
      - "Para el pago de pension a menores" -> `found_answer=False`,
        respuesta honesta de "no encontre informacion" (no hay ley de
        pensiones alimenticias cargada todavia).
      - "Sobre evasion de impuestos en Chiapas?" -> **hallazgo real**: el
        retrieval marco `found_answer=True` (paso el threshold de similitud
        con chunks de Adopcion/Tortura/Bibliotecas, ninguno relacionado a
        impuestos), pero el LLM generador NO alucino: reconocio
        explicitamente que los fragmentos recibidos no tienen relacion con
        impuestos y respondio que no puede contestar eso. El guardrail de
        contenido (system prompt estricto, Fase 2.5) funciono como segunda
        linea de defensa cuando el threshold de retrieval (Fase 2, 0.5) dejo
        pasar chunks irrelevantes. No es alucinacion, pero es evidencia real
        de que el threshold necesita mas ajuste con un corpus mas grande —
        anotado como pendiente en Fase 2 (dense/sparse weight tuning) en vez
        de "arreglado ya", para no ocultar el hallazgo `[Subagente: bugs]`
        si se retoma.
      Sin errores de bot: DB, embeddings, LLM, guardrails y persistencia
      funcionaron de punta a punta con trafico real `[Subagente: bugs]`
      confirmado, no hizo falta intervenir.
- [x] `/areas` completado — antes era literal `"Areas del derecho
      disponibles: en configuracion."`. Ahora `build_areas_message()` en
      `telegram_bot.py` consulta `documents.area_derecho`/`nombre` reales
      (`is_active=true`) y agrupa por area. Probado contra la DB real:
      devuelve las 4 leyes cargadas agrupadas en Cultural, Derechos humanos,
      Familiar, Penal — se actualiza solo si se cargan mas leyes, sin tocar
      este archivo `[Subagente: logic]`
- [x] Persistencia en Postgres (`conversations`, `messages`) — ya verificada
      extensamente en las pruebas de Fase 2.6/6 (`handle_turn()` se probo
      varias veces con conversaciones reales de 2+ turnos, incluyendo
      limpieza de datos de prueba despues de cada corrida) `[Subagente: database]`
- [x] Rate limiting — se reusa `app/api/rate_limit.py` (ya existente,
      construido por otra sesion para `chat_web.py`: ventana deslizante en
      memoria, 10 peticiones/60s por sesion). Se conecto tambien en
      `telegram_bot.py handle_message()`, con una salvedad importante:
      `enforce_rate_limit()` levanta `HTTPException`, pensada para un
      endpoint FastAPI directo — en el bot no hay un cliente HTTP esperando
      esa excepcion, asi que se atrapa y se responde por Telegram con
      `RATE_LIMIT_MESSAGE` en vez de dejarla subir (si subiera, rompería
      `handle_update()` y el webhook no devolveria 200 a tiempo, causando
      que Telegram reintente el mismo update). Verificado sin gastar
      llamadas reales: se agoto el limite manualmente para un chat_id de
      prueba y se confirmo que `handle_message()` corta ANTES de tocar la
      DB/LLM `[Subagente: security]`

**Entregable: COMPLETO.** Bot funcional en Telegram real (`@LexChiapasBot`),
probado de punta a punta con el usuario interactuando en vivo via modo
polling: webhook seguro, `/areas` real, persistencia verificada, rate
limiting conectado, guardrails rechazando preguntas fuera de dominio, y
generacion con cita real para preguntas dentro del dominio. Pendiente
opcional (no bloquea el entregable): registrar el webhook real en vez de
polling cuando el proyecto se despliegue con un dominio HTTPS publico; y el
ajuste de threshold anotado arriba, que se retoma en Fase 2.

---

## Fase 3.5 — Formato de salida por canal (asteriscos) — OBLIGATORIO

Documento fuente completo: **`LexChiapas_Formato_y_Mejoras_Futuras.md`**
(raiz del repo), Parte 1. Problema real: los LLM meten Markdown
(`**negrita**`) por costumbre, pero Telegram/WhatsApp no usan la misma
sintaxis que el LLM genera, asi que los asteriscos se muestran literales. El
documento marca esto como obligatorio, a diferencia de la Parte 2 (mejoras
RAG futuras, ver nota dentro de Fase 6).

**Defensa en 2 capas, ambas necesarias (no confiar solo en la capa 1):**

- [x] Capa 1 — System prompt: agregada seccion "REGLAS DE FORMATO" en
      `app/rag/generator.py SYSTEM_PROMPT` (texto plano, sin asteriscos,
      Markdown, encabezados `#` ni listas con guion/numero)
      `[Subagente: logic]`
- [x] Capa 2 — Backend (la garantia real, ~100% confiable): nuevo modulo
      `app/bots/output_formatter.py`, funcion `clean_markdown()` — Opcion A
      del documento (texto plano): quita `**negrita**`, `*cursiva*`,
      `__negrita__`, `_cursiva_`, encabezados `#`, codigo inline con
      backticks, y cualquier asterisco suelto que no formo par. Opcion B
      (traducir a sintaxis nativa de cada plataforma) queda pendiente como
      mejora opcional futura, no bloquea el entregable `[Subagente: logic]`
- [x] Aplicado en `telegram_bot.py TelegramBot.send_message()` — unico punto
      de salida hacia la API de Telegram, asi que cubre TODO mensaje sin
      importar quien lo llame (`/areas`, respuestas del RAG, rate limit,
      etc.) `[Subagente: bugs]` no hizo falta intervenir
- [x] Probado con una respuesta REAL con markdown (no sintetica): se tomo
      del `Message.id=45` guardado en la prueba en vivo de Fase 3 (el LLM
      escribio `**Ley Estatal para Prevenir y Sancionar la Tortura del
      Estado de Chiapas**` y `**Articulo 3**`), se corrio por
      `clean_markdown()` y salio sin ningun `**`/`*`, texto limpio y
      legible. `pytest tests/ -q` sigue en 13/13 `[Subagente: bugs]`
      confirmado, no hizo falta intervenir

**Entregable: COMPLETO.** Ninguna respuesta de Telegram muestra asteriscos ni
simbolos de Markdown crudos, verificado contra una respuesta real generada
por el LLM (no un caso inventado). `whatsapp_bot.py` no existe todavia
(Fase 5) — cuando se implemente, debe llamar a
`app.bots.output_formatter.clean_markdown()` igual que Telegram antes de
enviar.

---

## Fase 3.6 — Expansion del corpus (mas leyes)

Motivada por hallazgos reales de Fase 3: durante la prueba en vivo con el
usuario, preguntas sobre "evasion de impuestos" y "pago de pension a
menores" no encontraron ley cargada (el corpus de Fase 1/2 solo tiene 4
leyes: Amnistia, Bibliotecas, Tortura, Adopcion — un area distinta cada una,
sin cubrir familiar/pension, fiscal, laboral, civil, salud, etc.).

El subagente `data-extraction` investigo y verifico 10 leyes candidatas
reales contra Consejeria Juridica/Congreso (no inventadas — ver detalle
completo en el historial de esta sesion; resumen abajo). Prioridad 1-10
segun que tanto cubre un hueco confirmado + que tan viable es de procesar
(tamano/estructura razonable para el chunker):

- [x] 1. Codigo de Atencion a la Familia y Grupos Vulnerables (`familiar`) —
      CARGADO (document_id=10, 301 articulos, 333 chunks). **Hallazgo real:**
      esta ley NO cubre pension alimenticia/patria potestad como se esperaba
      — el propio texto dice que esos capitulos fueron DEROGADOS en 2015
      (P.O. 17-jun-2015) y transferidos a la Ley de los Derechos de Ninas,
      Ninos y Adolescentes. Verificado con dense_search real (threshold
      produccion 0.5): la pregunta de pension alimenticia SI pasa el umbral
      con 6 chunks de esta ley (Art. 2, 5, 11, 14, 147, similarity 0.50-0.53),
      pero el LLM responde honestamente que solo hay menciones generales, sin
      monto especifico — no alucina `[Subagente: data-extraction]` completado
- [x] 1b. (agregada fuera de la lista original de 10, motivada por el
      hallazgo de arriba) Ley de los Derechos de Ninas, Ninos y Adolescentes
      del Estado de Chiapas (`familiar`) — CARGADO (document_id=11, 190
      articulos, 312 chunks). URL real confirmada en Consejeria
      Juridica/Congreso (host `institutodelaconsejeriajuridica.chiapas.gob.mx`,
      el host viejo da 404 para esta ley). Articulos 111/135/121 sobre
      derechos alimentarios y patria potestad pasan el threshold real (0.52-
      0.54) para la pregunta de pension alimenticia. **Hallazgo real:**
      tampoco esta ley trae un MONTO especifico de pension alimenticia —
      solo principios/obligaciones generales. El detalle numerico
      probablemente vive en el Codigo Civil de Chiapas (item 10 de esta
      lista), aun no cargado `[Subagente: data-extraction]` completado
- [x] 2. Codigo Fiscal del Estado de Chiapas (`fiscal`) — CARGADO
      (document_id=13, 494 articulos, 974 chunks). URL real NO estaba en
      Consejeria Juridica (ni host viejo ni nuevo) — se encontro en el HTML
      crudo de la pagina del Congreso (el link estaba en un `onclick`, no
      visible al WebFetch normal, hubo que hacer `curl` + grep):
      `https://www.congresochiapas.gob.mx/new/Info-Parlamentaria/LEY_0007.pdf?v=MzE=`
      Confirmada con HEAD (200, Content-Length exacto). **2do bug real
      encontrado y corregido en `app/rag/chunker.py`:** `ARTICULO_RE` no
      manejaba sufijos con guion de articulos adicionados por reforma
      (`Articulo 278-A`, `278-B`), los colapsaba a ambos como `articulo_numero
      ="278"` — mala atribucion de cita, mismo riesgo #1 del proyecto. Solo
      afectaba 2 de 494 articulos de esta ley. Verificado independientemente
      (no solo el reporte del agente) con un caso sintetico: 278 y 278-A
      ahora quedan como chunks separados con numero correcto. **Nota:** este
      fix no trajo un test de regresion nuevo (a diferencia del bug de
      Movilidad #3) — pendiente menor, no bloquea. `pytest tests/` 14/14
      confirmado por mi de forma independiente despues del fix. **Hallazgo
      real de retrieval (no de chunking):** la pregunta literal "sanciones
      por evasion de impuestos" no trae los articulos correctos (217, 202)
      en el top-8 con threshold 0.5 — quedan opacados por articulos de otras
      leyes con score mas alto por casualidad de vocabulario. Preguntas con
      terminologia legal mas precisa ("defraudacion fiscal en Chiapas") SI
      traen el articulo correcto arriba (0.641). Es un gap real de calidad
      de retrieval para lenguaje coloquial, anotado para `rag-quality`, no
      arreglado aqui (fuera de alcance de ingesta) `[Subagente:
      data-extraction]` completado
- [x] 3. Ley de Movilidad y Transporte (`transito`) — CARGADO (document_id=12,
      160 articulos, 227 chunks). URL real confirmada en host nuevo
      `institutodelaconsejeriajuridica.chiapas.gob.mx` (el host viejo dio
      404, mismo patron que las leyes anteriores). Retrieval real
      (threshold 0.5) para "que necesito para sacar una licencia de
      conducir en Chiapas" -> Articulo 64 (sim=0.537, lista de requisitos)
      arriba del umbral. **Bug real encontrado y corregido en
      `app/rag/chunker.py`:** el PDF trae un typo real de la fuente,
      "Articulos 145.-" (plural) en vez de "Articulo 145.-", y
      `ARTICULO_RE` solo aceptaba la forma singular -- el Articulo 145 se
      tragaba silenciosamente dentro del contenido del 144 (exactamente el
      riesgo #1 del proyecto: chunking malo). Se corrigio haciendo la "S"
      final opcional (`ARTICULOS?`), se agrego test de regresion con el
      texto real del PDF en `tests/test_chunker.py`. Confirmado
      independientemente: `pytest tests/` 14/14 despues del fix
      `[Subagente: data-extraction]` completado
- [x] 4. Ley de Salud del Estado de Chiapas (`salud`) — CARGADO
      (document_id=14, 400 articulos, 471 chunks). URL real en host nuevo
      (mismo patron). **3ra y 4ta ronda de bugs reales de chunker
      encontrados** (documento de 136 paginas, el mas grande hasta ahora):
      (a) `TITULO_RE`/`CAPITULO_RE`/`SECCION_RE` de una sola palabra
      colapsaban 7 titulos compuestos distintos ("TITULO DECIMO" .. "TITULO
      DECIMO SEXTO") bajo el mismo valor `titulo="DECIMO"` (62% de los
      chunks afectados) y ademas matcheaban referencias a mitad de oracion
      como limite nuevo; (b) `ARTICULO_RE` no soportaba sufijos ordinales
      latinos separados por ESPACIO ("ARTICULO 117 BIS", hasta "117
      QUADRAGINTA" -- 94 articulos reales desaparecian fusionados); (c) el
      ruido de salto de pagina (numero de pagina suelto + nombre de la ley
      repetido, distinto del patron ya cubierto por `FOOTER_RE`) rompia la
      heuristica de "cita a mitad de oracion" justo despues de cada salto de
      pagina, fusionando articulos completos (caso real: Articulo 41
      desaparecia dentro del Articulo 40). El agente NO toco `chunker.py`
      compartido (choco con la edicion concurrente del agente de Codigo
      Fiscal) y en su lugar reimplemento estos 3 fixes en un chunker LOCAL
      dentro de `ingestion/load_ley_salud.py`, dejando el archivo compartido
      sin estos fixes. **Consolidado despues por mi (no por el agente):**
      porte los 3 fixes a `app/rag/chunker.py` (TITULO/CAPITULO/SECCION con
      validacion de linea completa via `_match_header()`/`_HEADER_LABEL_RE`;
      tercer grupo opcional en `ARTICULO_RE` para sufijo separado por
      espacio; filtro generico de salto de pagina armado dinamicamente desde
      `document_nombre`, no hardcodeado a esta ley), para que las leyes
      SIGUIENTES (sobre todo el Codigo Civil, #10, muy grande) no repitan el
      mismo problema con un chunker local ad-hoc cada vez. Agregue 2 tests
      de regresion con texto real (`test_real_document_midsentence_titulo_
      reference_does_not_split_chunk`, `test_real_document_compound_titulo_
      and_space_separated_articulo_suffix`) en `tests/test_chunker.py`
      (ahora 10 tests). Verificado independientemente: `pytest tests/`
      16/16, y re-corri `chunk_legal_text()` (la version YA fusionada) sobre
      el `.txt` completo real de esta ley -- reproduce exactamente los
      mismos numeros que el chunker local del agente (400 chunks, 0 sin
      articulo_numero, 0 duplicados, 7 titulos DECIMO* distintos + NOVENO
      BIS, ya no colapsados) -- no hizo falta re-ingestar la ley, los datos
      ya en la DB coinciden con lo que el chunker compartido produce ahora.
      **Hallazgo real de retrieval (no de chunking):** el articulo mas
      directamente relevante para "cuales son mis derechos como paciente"
      (Articulo 40) pasa el threshold real (0.522) pero queda fuera del
      top-8 con dense_search solo, superado por articulos mas genericos de
      "derecho a la salud" -- mismo tipo de gap anotado para Codigo Fiscal,
      pendiente para `rag-quality` `[Subagente: data-extraction]` completado
      + consolidacion de chunker hecha por mi directamente
- [x] 5. Ley del Servicio Civil del Estado y los Municipios (`laboral`) —
      CARGADO (document_id=16, 168 articulos, 233 chunks). **Hallazgo real
      importante:** el host nuevo tenia DOS archivos distintos con el mismo
      nombre segun si el espacio venia como "_" o "%20" -- uno con reformas
      hasta dic-2024 (el correcto), otro una copia vieja solo hasta dic-2020.
      El agente descargo ambos y comparo la fecha de "ultima reforma" DENTRO
      del texto de cada PDF antes de elegir, en vez de confiar en el nombre
      de archivo. Retrieval real (threshold 0.5) para "derechos si me
      despiden de un trabajo del gobierno" -> Articulo 43 y 51 relevantes,
      similarity ~0.55. **5to y 6to bug real de chunker, corregidos
      directo en el archivo compartido (no en copia local, como se pidio):**
      (a) `SECCION` es femenino en espanol ("SECCION PRIMERA", nunca
      "SECCION PRIMERO") pero `_ORDINAL_WORD` solo tenia formas masculinas
      -- 7 de 9 secciones de este documento no se reconocian; (b) varios
      encabezados de Capitulo/Seccion traen el titulo descriptivo pegado en
      la MISMA linea que el ordinal ("CAPITULO CUARTO DE LAS PRUEBAS") en
      vez de en su propia linea -- se agrego un match "flexible" de
      prefijo ordinal, protegido por la misma heuristica de mitad-de-oracion
      que ya usa ARTICULO_RE. El agente tambien encontro y corrigio un bug
      propio de codicia de regex que introdujo al escribir el fix
      (`[IVXLCDM]+` matcheando la "D" suelta de "DE"). Agrego 2 tests de
      regresion con texto real; suite paso de 10 a 18 tests. Verificado
      independientemente por mi: `pytest tests/` 18/18 despues
      `[Subagente: data-extraction]` completado
- [x] 6. Ley de Transparencia y Acceso a la Informacion Publica
      (`administrativo`) — CARGADO (document_id=17, 190 articulos, 294
      chunks). URL real en host nuevo (host viejo 404, mismo patron).
      Retrieval real (threshold 0.5): el articulo mas directamente relevante
      (123, procedimiento de solicitud) quedo justo debajo del umbral
      (0.4713) para la pregunta literal de prueba -- limitacion real de
      dense-only, no bug de ingesta (el pipeline de produccion usa
      hybrid_search con BM25, no se valido si eso lo resuelve). **Problema
      real encontrado y corregido, pero FUERA de chunker.py a proposito:**
      el Articulo 72 termina sin punto final justo antes del encabezado
      real del Articulo 73, disparando la heuristica de "cita a mitad de
      oracion" y fusionando el Articulo 73 completo dentro del 72. El
      agente confirmo que es un typo AISLADO de este PDF (no un patron
      estructural que afecte otras leyes) y lo corrigio con un reemplazo de
      texto exacto y documentado en su propio script de ingesta
      (`_normalize_raw_text`, no-op si el texto no coincide exacto), en vez
      de modificar la heuristica compartida ya validada contra 9 leyes
      reales -- buen criterio para no sobre-generalizar un caso puntual.
      Tambien intento un fix en chunker.py para el mismo bug de "Seccion
      femenina" que el agente de Servicio Civil, choco con esa edicion
      concurrente, reintento y confirmo que ya estaba resuelto en vez de
      duplicar trabajo `[Subagente: data-extraction]` completado
- [x] 7. Ley del Notariado (`civil`) — CARGADO (document_id=15, 277
      articulos, 306 chunks). Sin problemas reales: formato estandar (ya
      cubierto por el chunker existente), no hizo falta tocar nada.
      Retrieval real (threshold 0.5) para "que necesito para hacer un
      testamento en Chiapas" -> 8 resultados, todos de esta ley, similarity
      0.53-0.58, sobre testamentos/sucesion `[Subagente: data-extraction]`
      completado
- [x] 8. Codigo de la Hacienda Publica (`fiscal`) — CARGADO originalmente
      como document_id=18 (528 articulos, 989 chunks), **luego DESACTIVADO
      por mi (`is_active=False`, no borrado) tras verificar un hallazgo real
      de duplicado exacto** con el item #2 (Codigo Fiscal, document_id=13).
      El agente de ingesta lo detecto y lo reporto en vez de ignorarlo: el
      PDF de Congreso usado para "Codigo Fiscal" (id=13) y el PDF de
      Consejeria Juridica usado para "Codigo de la Hacienda Publica" (id=18)
      comparten la MISMA fecha de creacion (18-may-2016) y **texto de
      articulo IDENTICO palabra por palabra** (verificado por mi de forma
      independiente comparando Articulo 217 y Articulo 348 completos entre
      ambos .txt extraidos, no solo confiando en el reporte del agente). El
      preambulo/considerandos del PDF de Congreso (id=13) explica que el
      antiguo "Codigo de la Hacienda Publica" de 1999 (que combinaba Codigo
      Fiscal + Ley de Hacienda + Ley de Coordinacion Hacendaria + Ley de
      Presupuesto y Gasto Publico + Ley de Deuda Publica en un solo cuerpo)
      fue reordenado y renombrado en 2016 a "Codigo Fiscal del Estado de
      Chiapas" via Decreto 212 -- pero sigue cubriendo TODO el contenido
      original (incluye articulos de presupuesto de egresos, no solo temas
      fiscales, pese al nombre). El PDF de Consejeria Juridica (id=18)
      parece ser una copia desactualizada que nunca reflejo ese renombre:
      NO tiene el preambulo legislativo, se autodeclara con el nombre viejo
      ("III. Codigo: El Codigo de la Hacienda Publica..."), y su fecha de
      "ultima reforma" es mas vieja (22-ene-2025) que la de Congreso
      (10-dic-2025) -- la fuente legislativa oficial (Congreso) esta mas
      actualizada. **Decision (mi juicio, no un hecho legal verificado con
      una tercera fuente -- si el usuario tiene evidencia de lo contrario,
      corregir):** desactive id=18 y dejo id=13 (Codigo Fiscal) como la
      unica fuente activa para este contenido. Verificado despues de
      desactivar: `dense_search` para "como se elabora el presupuesto de
      egresos en Chiapas" ya solo devuelve chunks de "Codigo Fiscal del
      Estado de Chiapas" (Articulo 348 incluido), sin duplicados. `documents.
      is_active` ya estaba filtrado correctamente en `retriever.py` (linea
      49 dense, linea 76 sparse) -- no hizo falta cambiar codigo, solo el
      dato `[Subagente: data-extraction]` completado + correccion de
      integridad de datos hecha por mi directamente
- [x] 9. Ley Ambiental (`ambiental`) — CARGADO (document_id=19, 237
      articulos, 352 chunks). URL real en host nuevo (host viejo 404, mismo
      patron). Sin bugs de chunker ni de duplicado -- chunkeo limpio al
      primer intento, decreto/fechas distintas a las 13 leyes ya cargadas.
      Retrieval real (threshold 0.5) para "que hago si mi vecino esta
      contaminando un rio en Chiapas" -> 8 resultados relevantes (Articulo
      8 descargas de aguas residuales, 161/162 contaminacion del agua, 221
      riesgo de dano ambiental, 219 sanciones), similarity 0.514-0.539
      `[Subagente: data-extraction]` completado
- [x] 10. Codigo Civil para el Estado de Chiapas (`civil`) — CARGADO,
      particionado en 4 documentos por LIBRO (decision confirmada por el
      usuario: partir en vez de un solo documento). Reconocimiento manual
      previo (por mi, antes de lanzar los agentes) confirmo la estructura
      real: 4 Libros (Primero-Personas, Segundo-Bienes, Tercero-Sucesiones
      con encabezado espaciado "L I B R O T E R C E R O", Cuarto-
      Obligaciones), ~3000 articulos totales. 4 agentes en paralelo, cada
      uno con limites de texto exactos verificados por mi de antemano:
      - Libro Primero (De las Personas): document_id=20, 757 articulos, 802
        chunks. Sin bugs nuevos de chunker.
      - Libro Segundo (De los Bienes): document_id=21, 539 articulos, 554
        chunks. Typo puntual del PDF ("CAPIULO (SIC) I") corregido en el
        script de ingesta, sin tocar el chunker compartido.
      - Libro Tercero (De las Sucesiones): document_id=22, 493 articulos,
        497 chunks. Sin bugs nuevos.
      - Libro Cuarto (De las Obligaciones, el mas grande): document_id=23,
        1293 chunks guardados. Encontro y corrigio un bug real de
        TRANSITORIOS en el chunker COMPARTIDO (2 tests de regresion
        nuevos: `test_real_document_plural_articulos_transitorios_header_
        suppresses_numeric_transitorios`,
        `test_real_document_nothing_reopens_a_chunk_after_transitorios_
        boundary`), verificado por mi: `pytest tests/test_chunker.py`
        14/14 despues.
      Corpus final de Fase 3.6: **17 leyes activas, 7746 chunks totales**
      `[Subagente: data-extraction]` completado + reconocimiento de
      estructura hecho por mi directamente

Descartado en la investigacion (no incluir sin verificar de nuevo despues):
no existe una "Ley de Proteccion al Consumidor" estatal (es materia federal
via PROFECO); Justia Mexico devolvio HTTP 403 al consultarlo, no se pudo
confirmar su listado; ASE Chiapas no se reviso (su catalogo es de
fiscalizacion/auditoria, no leyes sustantivas de interes ciudadano).

**Como trabajarla:** esta fase corre EN PARALELO a Fase 4 (Celery), no la
bloquea ni la sigue en orden secuencial — usar el subagente
`data-extraction` para cada ley (parse -> chunk -> embed -> guardar,
verificando conteo/calidad de chunks antes de pasar a la siguiente) mientras
el hilo principal avanza Fase 4. Revisar cada ley cargada contra el checklist
de calidad de chunking de Fase 1 antes de darla por buena.

**Entregable: COMPLETO.** Corpus con 11 areas de derecho cubiertas (vs. 4 al
inicio de esta fase), 17 leyes activas, 7746 chunks totales, incluyendo las
dos que fallaron en la prueba real de Fase 3 (familiar/pension y fiscal).

---

## Fase 3.7 — Refuerzos post-expansion del corpus

Documentos fuente completos: **`LexChiapas_Reranker_y_Cache_Semantico.md`**
y **`LexChiapas_Refuerzos_Pendientes.md`** (raiz del repo) — ambos revisados
y verificados contra el estado real del codigo en esta sesion (no solo
leidos y asumidos ciertos), con hallazgos que actualizan/corrigen partes de
lo que proponen. Lista de prioridades acordada con el usuario:

1. ~~Terminar Codigo Civil~~ (ver item 10 de Fase 3.6, completo)
2. ~~Golden dataset~~ (ver abajo, completo)
3. ~~Manejo de errores en el pipeline de chat~~ (ver abajo, completo)
4. ~~Scraper de Congreso~~ (prioridad subida, ver abajo, completo -- no
   hacia falta Playwright, era un bug de selector)
5. ~~Reranker real~~ + investigacion de causas raiz + 2 fixes medidos (ver
   abajo, completo -- golden dataset 17/2/5 -> 19/2/3)
6. Cache semantico (depende del reranker)
7. Auditoria de seguridad de contenido scrapeado (sin trabajo nuevo)

- [x] **Golden dataset / set de regresion** — `tests/test_rag_regression.py`
      (24 preguntas reales, sin mocks, contra el pipeline en produccion y
      NVIDIA NIM real), cubriendo las 11 areas de derecho activas (no solo
      las 4 leyes originales, el documento fuente estaba desactualizado en
      eso). Corrida completa real (34m47s, explicable por el volumen de
      llamadas + fallback de hasta 5 modelos con 60s de timeout cada uno):
      **17 passed, 2 xfailed (limitaciones de retrieval ya conocidas), 5
      failed** (hallazgos reales documentados con evidencia, no bugs
      ciegos -- ningun articulo inventado en ninguna de las 24 corridas).
      Detalle completo en el archivo de test y en Fase 2 (linea ~319)
      `[Subagente: logic]` completado
- [x] **Manejo de errores en el pipeline de chat** — confirmado el gap real
      (cero `try/except` alrededor de `answer_question()`, una excepcion
      real perdia la pregunta del usuario sin dejar rastro) via
      `[Subagente: bugs]`, arreglado por mi directamente:
      - Columna nueva `messages.error_message` (Text, SQL directo -- el
        proyecto no tiene alembic/migraciones, se agrego igual que las
        columnas anteriores)
      - `found_answer` ahora es un estado de 3 valores real: `True`
        (respondio), `False` (busco y no encontro -- legitimo), `None`
        (excepcion real, el pipeline nunca llego a decidir)
      - `app/bots/conversation_store.py handle_turn()` envuelve
        `answer_question()` en try/except: persiste el error con traceback
        completo en `error_message`, hace `db.rollback()`, devuelve un
        `ChatResponse` con mensaje amigable y `system_error=True` (campo
        nuevo en `app/schemas/chat.py`) en vez de dejar que la excepcion
        suba y tire 500. Como es el UNICO punto de entrada compartido por
        Telegram y el chat web, ninguno de los dos canales necesito cambios
        propios.
      - Probado end-to-end con una excepcion real forzada (no solo leido el
        codigo): confirmado que la pregunta del usuario queda persistida,
        el error queda distinguible, y la respuesta al usuario es
        amigable, sin 500.
      - Resuelve directamente `WEB_FRONTEND_PLAN.md` items #3 y #14
        (bloqueados en backend hasta ahora)
- [x] **Scraper de Congreso** (`ingestion/scrapers/congreso_scraper.py`) —
      **hallazgo real que corrige la premisa original**: NO hacia falta
      Selenium/Playwright. La suposicion de que el listado se cargaba por
      JavaScript (documentada en una sesion anterior) resulto INCORRECTA al
      reverificar contra el sitio real -- el listado SI esta en el HTML
      estatico, el scraper viejo fallaba porque el link al PDF vive en el
      atributo `onclick="goToUrl('...')"` de cada `<tr>`, no en un
      `<a href>` (el `<a>` de la celda es solo un icono sin `href`). Nunca
      se agrego la dependencia nueva `[Subagente: data-extraction]`,
      verificado de forma independiente antes de aceptar el hallazgo (no
      solo el reporte del agente):
      - `list_available_laws()` reescrito con regex sobre `onclick` +
        BeautifulSoup, mismo contrato de retorno que
        `consejeria_scraper.py` (`[{"nombre", "source_url"}]`)
      - Corrida real independiente: **146 leyes** encontradas contra el
        sitio en vivo (confirmado dos veces, por el agente y por mi
        directamente)
      - `download_pdf()` verificado con una descarga real independiente
        (Codigo Fiscal del Estado de Chiapas, 1.93 MB, firma `%PDF-`
        valida)
      - Comparacion contra la tabla `documents` real (17 activos):
        **los 17 tienen match** en el listado de Congreso (0 sin match,
        verificado con mi propia query normalizando acentos/mayusculas,
        no solo el reporte del agente) -- incluyendo Codigo Fiscal del
        Estado de Chiapas, que ya estaba cargado correctamente. El caso
        historico que motivo subir la prioridad de este item (Codigo
        Fiscal ausente de Consejeria pero presente en Congreso) ya estaba
        resuelto desde la Fase 3.6 (deduplicacion Fiscal/Hacienda Publica)
      - **132 leyes** (conteo propio; el agente reporto 129, diferencia
        minima de heuristica de matching, no material) existen en Congreso
        pero NO estan en la DB -- esperado, es la diferencia entre el
        catalogo completo del estado y el subconjunto acotado con el que
        arranco el proyecto a proposito (ver "Fuentes de datos" en
        CLAUDE.md). Entre ellas: Codigo Penal para el Estado de Chiapas,
        Codigo de Procedimientos Civiles, Codigo de Procedimientos
        Penales, Codigo Fiscal Municipal, y ~128 leyes/decretos mas.
        **NO se ingirio nada nuevo a la DB** -- decidir que cargar (y
        evitar duplicados como el caso Fiscal/Hacienda, que requirio
        comparar texto articulo por articulo a mano) es una decision
        pendiente de revision humana, no automatizada aqui a proposito
      - Codigo Penal para el Estado de Chiapas en particular es
        directamente relevante: es la ley cuya ausencia genera el
        `test_no_encontrado_codigo_penal` del golden dataset -- ahora hay
        una via real y verificada para cerrar ese hueco si se decide
        expandir el corpus
        `[Subagente: data-extraction]`, verificado independientemente por
        mi (re-corrida del scraper, descarga de PDF, y comparacion contra
        la DB real, no solo el reporte del agente)
- [x] **Codigo Penal para el Estado de Chiapas cargado al corpus** — primera
      ley agregada usando el scraper de Congreso recien arreglado (URL real:
      `LEY_0012.pdf`, confirmada arriba). Cierra directamente el hueco que
      documentaba `test_no_encontrado_codigo_penal` (ahora
      `test_penal_codigo_penal_robo`, ver abajo). Segunda ley del area
      `penal` (la primera era Ley de Amnistia, doc 4) -- documento id=24.
      - **561 articulos, 801 filas de chunks** en la DB (algunos articulos
        largos se dividen en varias piezas de embedding, comportamiento
        esperado del chunker). Spot-check de 4 chunks al azar (Art. 40,
        385, 51, 23): metadata de Titulo/Capitulo/Seccion correcta
      - **Bug real de chunker encontrado y arreglado en el modulo
        COMPARTIDO** (no forkeado): `_is_midsentence_line` en
        `app/rag/chunker.py` trataba cualquier encabezado como
        continuacion de mitad de oracion si la linea de contenido anterior
        no terminaba en `.`, `:`, `;` o `)`. El Art. 309 tiene un item de
        lista con letra ("c) Que sea cometido por un servidor publico...")
        SIN punto final -- typo real del PDF fuente -- asi que el Art. 310
        completo (tampering de mojoneras, con su propia sancion) se
        tragaba silenciosamente dentro del contenido del Art. 309 y
        desaparecia del chunking. Arreglado agregando `_ENUM_ITEM_RE`
        (matchea marcadores de lista con letra/romano/numero: `a)`,
        `II.-`, `1)`) como excepcion -- esas lineas cuentan como "cerradas"
        sin importar la puntuacion final, porque su propia estructura de
        lista ya delimita una unidad completa. Nuevo test de regresion
        `test_real_document_unpunctuated_enum_item_does_not_swallow_next_articulo`
        en `tests/test_chunker.py` con el excerpt real verbatim. 15/15
        tests de chunker pasan, sin regresiones (verificado
        independientemente, no solo el reporte del agente)
      - **MEDIDO end-to-end contra el pipeline real** (verificado dos
        veces, por el agente y por mi de forma independiente): "Cual es la
        pena por el delito de robo segun el Codigo Penal de Chiapas?" -->
        `grounded=True`, cita el **Articulo 270** real ("Comete el delito
        de robo, el que se apodere de una cosa mueble ajena...") con las
        fracciones de sancion correctas, mas articulos agravantes
        relacionados (276, 277, 281) -- todos articulos reales del Codigo
        Penal, sin alucinacion
      - `test_no_encontrado_codigo_penal` (ya no aplica, la premisa de que
        el Codigo Penal no estaba en el corpus dejo de ser cierta) renombrado
        a `test_penal_codigo_penal_robo`, convertido en test positivo real
        (assert `grounded is True` + Art. 270 en `retrieved_chunks`),
        docstring reescrito contando la historia real. `pytest
        tests/test_rag_regression.py -v -s -k codigo_penal` -- 1 passed,
        Art. 270 en posicion 1 (verificado independientemente, corrida
        propia con el semantic_cache limpio, 124.33s, generacion real no
        cacheada)
        `[Subagente: data-extraction]`, verificado independientemente por
        mi (query directa a `documents`/`chunks`, pregunta real contra el
        pipeline, y corrida propia del test actualizado)
- [x] **Reranker real** — ver `LexChiapas_Reranker_y_Cache_Semantico.md`
      para el checklist completo. Verificado en esta sesion: el modelo de
      NVIDIA propuesto originalmente en el documento
      (`nvidia/llama-3.2-nv-rerankqa-1b-v2`) esta MUERTO (410 Gone,
      end-of-life 2026-05-18). El usuario encontro el reemplazo correcto:
      **`nvidia/llama-nemotron-rerank-vl-1b-v2`**
      (`https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-nemotron-rerank-vl-1b-v2/reranking`),
      probado con una llamada real (query sobre tortura vs. chunk de
      bibliotecas, logit -3.0 vs -7.79, separacion correcta) -- funciona
      con texto solo, sin necesitar imagen aunque el nombre diga "vl"
      (vision-language). Jina (`jina-reranker-v2-base-multilingual`) tambien
      confirmado funcionando como 2do nivel de fallback. Hallazgo
      importante que el documento fuente NO menciona: el gate anti-
      alucinacion (`grounded`) se calcula en `dense_search` ANTES de que el
      reranker corra -- cambiar el reranker NO obliga a recalibrar
      `similarity_threshold` a menos que se decida ademas cambiar de que
      score depende el gate (diseño mas grande, no incluido aqui).
      **MEDIDO contra el golden dataset (no asumido)**, corrida completa real
      `pytest tests/test_rag_regression.py -v -s` con el reranker real ya
      activo (`nvidia/llama-nemotron-rerank-vl-1b-v2` -> Jina -> heuristica
      local), 24 preguntas, sin mocks, 1978.21s = 32m58s:
      **17 passed, 2 xfailed, 5 failed -- identico al baseline placeholder**
      (17/2/5, 34m47s). Comparacion resultado por resultado contra el
      baseline documentado en el docstring de
      `tests/test_rag_regression.py`:
      - **Cero regresiones**: ningun test que antes pasaba ahora falla, y
        ningun articulo inventado en ninguna de las 24 corridas (mismo
        resultado que antes en anti-alucinacion).
      - **Los 2 xfailed conocidos NO cambiaron de bucket** pero uno tiene un
        detalle real: `test_derechos_humanos_tortura_sanciones_limite_conocido`
        sigue XFAIL, con `grounded=True` y el Art. 3 de la Ley de Tortura en
        posicion 1 (sim=0.573) -- esto confirma en vivo que el gate
        `grounded` es independiente del reranker (se calcula en
        `dense_search` antes de que el reranker corra, como ya se anoto
        arriba), asi que el reranker no podia cambiar este resultado por
        diseño. `test_civil_sucesion_intestada_limitacion_conocida` (Art.
        1576, Libro Tercero) sigue XFAIL, articulo NO aparecio en el top-5
        (top-5 real: Art. 1533, 1321, 1308, 1334, 1282, todos de la misma
        ley/libro pero no el articulo exacto) -- **el reranker real NO
        resolvio esta limitacion de ranking**, sigue siendo el mismo
        problema documentado con el placeholder.
      - **Los 5 failed son los mismos 5 tests documentados**, con la misma
        causa raiz en cada caso, verificado con evidencia nueva (posicion y
        articulo real en el top-5 de esta corrida):
        - `test_familiar_adopcion_requisitos` (Art. 8, Ley de Adopcion):
          sigue sin aparecer en el top-5 (`posicion: None`). El top-5
          cambio de composicion (ahora Adopcion Art.12/3 SI entran, antes
          solo Codigo Civil) pero el articulo esperado sigue fuera --
          mismo solapamiento Codigo Civil / Ley de Adopcion documentado.
        - `test_familiar_adulto_mayor_definicion` (Art. 2, Codigo de
          Atencion a la Familia): sigue sin aparecer en el top-5 (mismo
          articulo de definiciones gigante diluyendo la señal semantica).
        - `test_no_encontrado_proteccion_consumidor`,
          `test_no_encontrado_codigo_penal`,
          `test_no_encontrado_proteccion_animal`: los 3 siguen dando
          `grounded=True` (falso positivo del gate) por lenguaje legal
          generico cruzando `similarity_threshold=0.5` -- este bug es de
          `dense_search`/threshold, corre ANTES del reranker por diseño, asi
          que el reranker no podia arreglarlo (consistente con el hallazgo
          documentado arriba de que el gate no depende del reranker).
      - **Conclusion honesta**: el reranker real esta funcionando en
        produccion (llamadas reales exitosas, ninguna senal de fallback a
        Jina o a la heuristica local en los logs de esta corrida completa --
        no aparecio ningun `logger.warning` de "reranking con 'X' fallo" en
        la salida de pytest, ni error de conexion/timeout hacia NVIDIA o
        Jina en ninguna de las 24 preguntas) y no causo ninguna regresion,
        pero **el golden dataset actual NO muestra una mejora medible**: las
        2 limitaciones de xfailed y los 5 failed tienen causa raiz en
        `dense_search`/threshold o en solapamiento real entre leyes, no en
        el metodo de reranking en si -- el reranker solo puede reordenar
        candidatos que YA pasaron el threshold de `dense_search`, y en
        estos 7 casos el articulo correcto o bien no pasa el threshold con
        suficiente margen (Art. 1576) o el problema esta upstream (gate de
        `grounded`). No se marca como "mejora confirmada", se documenta
        como "medido, sin regresion, sin mejora medible en este dataset" --
        posible candidato a revisar top-K de `dense_search` (subir de 20-30
        candidatos) antes de re-medir, no un problema del reranker mismo
        `[Subagente: logic]`
- [x] **Investigacion de causas raiz post-reranker + 2 fixes medidos** — el
      reranker no mostro mejora medible (ver arriba) porque las causas
      reales estaban aguas arriba, en `dense_search`/threshold, no en el
      metodo de reranking. Investigacion en vivo (`[Subagente: logic]`,
      queries reales contra la DB/embeddings de hoy, no solo relectura de
      comentarios viejos) confirmo/corrigio 3 hallazgos:
      - **Adulto mayor (Codigo de Atencion a la Familia Art.2)**: el chunk
        SI esta bien fragmentado (no es un articulo de 36 fracciones como
        se creia) pero caia en la posicion 16/30 -- un lugar FUERA del pool
        real de candidatos (`hybrid_search` usaba `k = top_k*3 = 15`).
        Nunca llegaba a competir en el reranker. Fix: `k = top_k*4` en
        `app/rag/retriever.py` (linea ~149).
      - **Sucesion intestada (Art. 1576, Libro Tercero)**: hallazgo NUEVO
        que contradice lo documentado antes -- hoy mide similitud 0.4765
        (bajo threshold=0.5) y esta en la posicion #1141 de 7746 chunks
        activos, no cerca del top-30. No es un problema de top-K/reranker,
        es el embedding de ese chunk puntual. Queda PENDIENTE (necesita
        reescritura de consulta o revision del chunk, el fix de `k` no lo
        alcanza).
      - **Bucket B (falsos positivos de `grounded`)**: confirmado que
        lenguaje legal generico de otras leyes cruza el threshold=0.5 en la
        banda 0.55-0.60 sin responder la pregunta real (proteccion al
        consumidor, Codigo Penal). Fix: nuevo modulo
        `app/rag/grounding.py` con `answer_is_explicit_refusal()` -- un
        SEGUNDO gate, posterior a la generacion, que degrada
        `grounded=True` a `False` si el LLM abrio la respuesta con una
        negativa explicita ("No puedo responder esa pregunta con los
        fragmentos..."). Nunca puede convertir False en True. Integrado en
        `app/rag/rag_pipeline.py` despues de `generate_answer()`.
      - **Bug real encontrado y corregido durante la propia medicion**: la
        primera version de `answer_is_explicit_refusal()` buscaba los
        patrones en el texto COMPLETO de la respuesta y genero un falso
        positivo real -- una respuesta de adopcion genuinamente fundamentada
        (Codigo Civil Art.385/397 con contenido real) incluia una frase de
        matiz en su penultimo parrafo ("los fragmentos no detallan todos
        los pasos...") que coincidio con los patrones y degrado a
        `grounded=False` una respuesta que si tenia fundamento. Corregido
        limitando la busqueda a los primeros 300 caracteres (`
        _REFUSAL_WINDOW_CHARS`) -- verificado con texto real que las
        negativas genuinas siempre abren la respuesta, mientras que las
        respuestas parcialmente sustantivas dejan cualquier matiz para el
        final.
      - **MEDIDO contra el golden dataset completo** (no asumido), corrida
        real `pytest tests/test_rag_regression.py -v -s`, 24 preguntas, sin
        mocks, 2643.82s = 44m03s (mas lento que el baseline por el `k`
        mayor -- mas candidatos, mas llamadas al reranker por consulta):
        **19 passed, 2 xfailed, 3 failed** -- mejora real de +2 passed / -2
        failed vs. el baseline del reranker (17/2/5). Sin regresiones
        nuevas: `test_familiar_adulto_mayor_definicion` y
        `test_no_encontrado_proteccion_consumidor` ahora pasan;
        `test_familiar_adopcion_requisitos` (solapamiento real con Codigo
        Civil), `test_no_encontrado_codigo_penal` (el LLM da una respuesta
        parcialmente sustantiva citando Codigo Fiscal Art.224, no una
        negativa pura -- el gate correctamente NO se dispara ahi, limite
        honesto del heuristico) y `test_no_encontrado_proteccion_animal`
        (no es un bug, contenido legitimo de Ley de Salud) siguen fallando
        exactamente por las mismas causas ya documentadas, sin cambios de
        comportamiento nuevos
- [~] **Art. 1576 (sucesion intestada) — investigado a fondo, fix barato
      aplicado, techo real confirmado** — el usuario eligio atacar este caso
      primero, con la opcion "ambos, empezando por el barato" entre dos
      caminos evaluados: (A) expansion de consulta determinista (rapida,
      sin tocar el corpus) vs. (B) prefijo de contexto Ley/Titulo/Capitulo
      + re-embed completo de los 7746 chunks (sistemico, caro, diferido).
      Causa raiz confirmada leyendo el documento fuente real: Art.1576 vive
      bajo `TITULO CUARTO / DE LA SUCESION LEGITIMA / CAPITULO I`, pero el
      chunker solo guarda el ordinal "CUARTO" como metadata, sin el texto
      descriptivo, y ese texto tampoco se incluye en lo que se embebe. El
      propio Art.1576 nunca dice "testamento" en su texto -- esa conexion
      vive en el Art.1573, dos articulos antes, en un chunk sin traslape
      lexico.
      Fix (A) implementado: `app/rag/legal_synonyms.py` (nuevo,
      `expand_legal_synonyms()`), reglas deterministas sin LLM que agregan
      terminos legales a la consulta de BUSQUEDA (nunca a la pregunta que
      ve el usuario) antes de embeber. Integrado en
      `app/rag/rag_pipeline.py` despues de `rewrite_query()` (Fase 6),
      ambos mecanismos componen. `app/rag/text_utils.py` (nuevo) extrae
      `strip_accents()` compartido con `app/rag/grounding.py`.
      **Medido en vivo, iterativo** (2 versiones de la regla, cada una
      verificada con `dense_search`/`hybrid_search` reales antes de
      aceptarla):
      - v1 (`"sucesion legitima herederos legitimos"`): subio Art.1573 de
        no aparecer en el top-30 a la posicion #1 (sim 0.66) -- el
        articulo que SI conecta "no hay testamento" con la apertura de la
        sucesion legitima. Art.1576 seguia sin aparecer.
      - v2 (agrega `"quienes tienen derecho a heredar orden de herederos"`,
        frase juridica estandar, no una copia literal del articulo): subio
        la similitud REAL de Art.1576 de 0.4765 (bajo threshold, posicion
        #1141 de 7746) a **0.5469 (SI cruza threshold=0.5 ahora), pero en
        la posicion #233 de 6757** -- muy fuera de cualquier `k` practico
        para `dense_search` sin disparar el costo por consulta. BM25
        tampoco lo discrimina ("sucesion legitima"/"heredar" son demasiado
        comunes en todo el Libro Tercero).
      - **Techo real confirmado**: el fix (A) mejora la respuesta de forma
        genuina y medible -- la generacion real ahora dice correctamente
        "al morir sin testamento se abre la herencia legitima" (citando
        Art.1573/1269) y ADMITE explicitamente que no puede especificar el
        orden de herederos con la informacion disponible (sin alucinar) --
        pero NO logra retornar el Art.1576 especifico. Cerrar esto de
        verdad requiere el fix (B) (prefijo de contexto + re-embed), que
        queda diferido tal como el usuario decidio.
      - **OPCION RECOMENDADA para cuando se retome esto** (propuesta, NO
        ejecutada -- el usuario pidio dejarla escrita para decidir despues):
        antes de comprometerse al re-embed completo del corpus (8500+
        chunks, costo real de API, riesgo de mover el ranking de casos que
        hoy funcionan bien), correr un EXPERIMENTO BARATO que prueba la
        hipotesis primero: re-embeber en memoria (sin tocar la DB de
        produccion) solo los ~15-20 chunks del Titulo Cuarto (De la
        Sucesion Legitima) del Libro Tercero, con un prefijo de contexto
        real agregado al texto antes de embeber (ej. "Codigo Civil de
        Chiapas, Libro Tercero, Titulo Cuarto -- De la Sucesion Legitima,
        Capitulo I:") y medir DIRECTO (comparando embeddings sueltos, sin
        insertar nada) si la similitud de Art.1576 contra la pregunta real
        sube lo suficiente para ser recuperable en la practica (necesitaria
        acercarse a un top-20/30, no solo cruzar el threshold=0.5 como paso
        con el fix A).
        - Si el experimento confirma mejora real: justifica (1) extender
          `app/rag/chunker.py` para capturar el texto descriptivo del
          Titulo/Capitulo (hoy solo se guarda el ordinal, ej. "CUARTO", sin
          "DE LA SUCESION LEGITIMA" -- ver hallazgo de la investigacion de
          causas raiz arriba) y (2) el re-embed completo del corpus como
          mantenimiento programado, con re-medicion del golden dataset
          completo despues (no asumir que ayuda solo a este caso, verificar
          que no mueve el ranking de otras preguntas)
        - Si el experimento NO muestra mejora suficiente: se documenta con
          evidencia real que el problema es mas profundo que el contexto de
          Titulo/Capitulo (posiblemente el propio Art.1576 necesita
          reescritura de contenido o un enfoque de retrieval distinto, ej.
          parent-child), y se evita gastar en un re-embed completo sin
          justificacion medida
      - **EXPERIMENTO CORRIDO (Fase 6, decision del usuario de correrlo ya
        en vez de dejarlo solo como opcion escrita)**: comparacion en
        memoria, sin tocar la DB, entre el formato real de produccion
        (`to_embedding_text()`: "..., Titulo CUARTO, Capitulo I, Articulo
        1576: ...") y el mismo formato con el texto descriptivo real del
        Titulo agregado ("Titulo CUARTO (De la Sucesion Legitima)").
        Primer intento tuvo un bug de metodologia (el "control" uso
        `chunk.content` crudo en vez de replicar `to_embedding_text()`,
        dando numeros que no coincidian con los historicos) -- corregido
        reconstruyendo el header exacto que usa produccion; el control
        correcto SI reprodujo los numeros historicos casi exacto (0.47648
        vs 0.4765 documentado, 0.54687 vs 0.5469), confirmando que el
        metodo ya es confiable.
        **Resultado real: NO ayuda.** Con el texto descriptivo agregado,
        la similitud contra la pregunta cruda subio de 0.47648 a 0.47815
        (+0.0017, dentro del ruido) y contra la pregunta ya expandida por
        `legal_synonyms` BAJO de 0.54687 a 0.54303 (-0.0038). El texto
        descriptivo del Titulo/Capitulo NO es la causa del problema real
        -- el gap semantico de Art.1576 es mas profundo (probablemente el
        propio texto del articulo, una lista corta de categorias de
        parientes sin lenguaje explicativo, generaliza mal en el espacio
        de embeddings sin importar que contexto se le anteponga).
        **Decision, siguiendo el plan ya escrito para el caso negativo: NO
        se procede con el re-embed completo del corpus** (8500+ chunks,
        costo real, sin justificacion medida) ni con extender el chunker
        para capturar texto descriptivo de Titulo/Capitulo -- esta via
        especifica de "Contextual Retrieval barato" queda CERRADA para
        este caso, documentada con evidencia real en vez de asumida. Art.
        1576 sigue como limitacion de retrieval conocida y aceptada; el
        contexto determinista actual (`to_embedding_text()`, ya incluye
        ley/titulo-ordinal/capitulo/articulo) se mantiene tal cual, no se
        toca `app/rag/chunker.py` por este hallazgo
        `[Yo directamente, con la correccion de metodologia incluida en el
        reporte, no ocultada]`
      - `pytest tests/test_rag_regression.py -v -s` completo, 24 preguntas,
        sin mocks, 337.70s = 5m37s (mucho mas rapido que corridas
        anteriores, sin patron claro de por que -- probablemente varianza
        real de latencia de NVIDIA/fallback entre corridas, no un cambio de
        codigo): **18 passed, 2 xfailed, 4 failed**. La prueba de sucesion
        sigue XFAIL (comportamiento esperado, no se preveia que pasara).
      - **Hallazgo lateral real, NO introducido por este fix**:
        `test_no_encontrado_proteccion_consumidor` paso en la corrida
        anterior (19/2/3) pero fallo en esta -- confirmado con 3 muestras
        reales adicionales de la misma pregunta que el gate de negativa
        explicita (`app/rag/grounding.py`, agregado en el trabajo anterior
        de esta sesion) tiene cobertura de patrones demasiado angosta: el
        LLM frasea la negativa de formas variadas ("no aparece ninguna
        disposicion", "no se encuentra informacion", "no encontre
        informacion") que los patrones actuales (enfocados en "no
        contiene/incluye informacion", "no puedo responder") no siempre
        capturan. Evaluado ampliar los patrones pero **descartado
        deliberadamente**: un patron mas amplio tipo "no se encuentra
        informacion especifica sobre X" tambien coincide con el caso
        `test_no_encontrado_proteccion_animal`, que NO deberia degradarse
        (ese caso SI tiene una respuesta parcial legitima en el corpus, ver
        hallazgo ya documentado arriba) -- ampliar el patron arreglaria un
        caso y romperia otro. Limitacion real y aceptada de un heuristico
        de texto sobre prosa de LLM no determinista: nunca va a tener 100%
        de cobertura sin un juicio mas fino que un regex (ej. un
        clasificador o un segundo LLM barato) que no se justifica todavia
        para este volumen de casos. Queda documentado, no oculto -- no se
        toco el gate para perseguir un numero de test especifico
        `[Yo directamente, con verificacion en vivo contra dense_search/
        hybrid_search/rag_pipeline reales antes y despues de cada cambio]`
- [x] **Gate de negativa explicita reemplazado por un clasificador LLM
      barato** — el usuario pidio explicitamente atacar la brecha anterior
      "con un enfoque distinto, ej. un segundo LLM barato de
      clasificacion" en vez de seguir ampliando regex. `app/rag/
      grounding.py` reescrito: `answer_is_grounded_in_practice(question,
      answer_text)` reemplaza `answer_is_explicit_refusal(answer_text)`.
      Criterio del prompt (2 iteraciones, ambas verificadas con casos
      reales antes de aceptarlas):
      - v1 ("responde de verdad lo que se pregunto") causo una regresion
        real: marco como NO fundamentada una respuesta legitima sobre
        sucesion (Art.1573, MISMO tema/libro que la pregunta, solo
        incompleta) -- confundia "incompleto" con "no fundamentado". El
        test que cubre ese caso exige `grounded=True` como requisito duro
        (gate anti-alucinacion, no completitud), asi que esto era un bug
        real, no solo una preferencia.
      - v2 (criterio corregido a MISMO tema/institucion juridica vs. tema
        DISTINTO ofrecido como consuelo): verificada contra 6 casos reales
        conocidos antes de aceptarla -- consumidor y codigo_penal (tema
        distinto) -> False; sucesion, adopcion, adulto_mayor (mismo tema,
        completo o incompleto) -> True.
      - **Hallazgo operativo real durante la implementacion**: la primera
        version uso un solo modelo/proveedor hardcodeado (Ministral-14b via
        nvidia_nim, igual que app.rag.query_rewriting) y las 5 llamadas de
        prueba fallaron por timeout -- diagnosticado en vivo: NVIDIA NIM
        tenia una degradacion de servicio REAL ese momento (confirmado con
        el error explicito de la API en otro modelo nvidia_nim, "DEGRADED
        function cannot be invoked", no un bug de este codigo ni rate
        limit). Corregido reusando `app.llm.router.generate_with_fallback`
        (NVIDIA NIM -> OpenAI -> xAI, la misma cadena multi-proveedor ya
        usada para la generacion principal) en vez de un cliente propio de
        un solo proveedor -- mismo criterio de resiliencia que el resto del
        pipeline, sin duplicar logica de fallback. El fallback silencioso a
        `True` (no degradar) funciono correctamente durante la degradacion
        real de NVIDIA, protegiendo el pipeline como estaba disenado.
      - **MEDIDO contra el golden dataset completo**, `pytest
        tests/test_rag_regression.py -v -s`, 24 preguntas, sin mocks,
        318.52s = 5m18s: **21 passed, 2 xfailed, 1 failed** -- mejora real
        vs. el resultado anterior de esta misma fase (19/2/3) y vs. el
        baseline original del reranker (17/2/5). El unico failed restante
        es `test_familiar_adopcion_requisitos` (Art.8 Ley de Adopcion vs.
        Codigo Civil, solapamiento real de dos leyes en el top-K, ya
        documentado arriba -- no es algo que ninguno de los fixes de hoy
        buscara resolver)
        `[Yo directamente, con verificacion en vivo del clasificador contra
        casos reales conocidos antes y despues de cada version del prompt,
        mas la corrida completa del golden dataset]`
- [x] **Revision de `LexChiapas_Grounding_Gate_Estructurado.md`** — el
      usuario aporto este documento (escrito antes de saber que el
      clasificador LLM de arriba ya funcionaba medido en 21/2/1) pidiendo
      evaluar viabilidad de sus 3 tareas + 1 nota final:
      - **Tarea 1 (found_answer estructurado en el schema de generacion,
        reemplazando el clasificador)**: NO implementada, decision
        explicita. Es un cambio mas grande y riesgoso (toca el prompt/
        schema del generador PRINCIPAL, el camino mas critico del
        sistema) para una ganancia de eficiencia (evitar la segunda
        llamada LLM) que no esta probada como necesaria -- el suite
        completo con el clasificador activo corrio en 5m18s/5m48s, mas
        rapido que corridas anteriores sin clasificador. El propio
        documento admite que no sabe si structured output funciona igual
        en los 5 proveedores del fallback -- eso habria que verificarlo
        desde cero. Se deja como opcion futura solo si la latencia/costo
        del segundo call se vuelve un problema medido, no ahora
      - **Tarea 2 (corregir expectativa de Adopcion Art.8)**: SI
        implementada. `tests/test_rag_regression.py::
        test_familiar_adopcion_requisitos` actualizado para aceptar
        CUALQUIERA de Ley de Adopcion Art.8 o Codigo Civil Art.385/397
        como fundamento valido (ambos ya verificados como respuestas
        correctas, no alucinadas, en corridas reales de esta sesion) --
        la expectativa vieja convertia un comportamiento correcto en una
        falla permanente
      - **Tarea 3 (re-correr y reportar conteo real)**: hecho, ver abajo
      - **Nota final (Art.1573 como regression guard permanente)**:
        confirmado que YA estaba protegido -- el `assert response.grounded
        is True` de `test_civil_sucesion_intestada_limitacion_conocida`
        es un assert DURO (no soft-check) que habria fallado con el bug
        real que causo la regresion (v1 del prompt del clasificador
        degradando el caso Art.1573). Se hizo explicito en un comentario
        nuevo en ese test documentando este doble proposito, para que no
        se pierda si alguien vuelve a tocar el prompt del clasificador sin
        saber que este assert lo protege
      - **MEDIDO** despues de Tarea 2, `pytest tests/test_rag_regression.py
        -v -s`, 24 preguntas, 348.89s = 5m48s: **21 passed, 2 xfailed, 1
        failed** -- mismo conteo neto que antes (Adopcion ahora pasa
        siempre, pero `test_no_encontrado_proteccion_animal` broto como
        flaky en su lugar)
      - **El usuario, correctamente, no acepto "caso ambiguo" sin evidencia
        de en que CAPA vivia la no-determinismo** -- pregunta clave: ¿vario
        el texto que genero el LLM principal entre corridas, o el
        clasificador dio veredictos distintos sobre el MISMO texto? Son
        escenarios con implicaciones distintas (el segundo es mucho mas
        grave -- el gate en si seria una moneda al aire). Diagnosticado con
        precision, en dos pasos:
        1. Clasificador con texto FIJO, `temperature=0.1` (heredado sin
           querer de la generacion principal): 5 llamadas identicas dieron
           **2x False y 3x True para el MISMO input** -- confirmado que el
           clasificador SI era no determinista, mas serio que un caso
           limite ambiguo. **Corregido**: `generate_with_fallback` (app/
           llm/router.py) ahora acepta un override `temperature` opcional;
           `answer_is_grounded_in_practice` lo usa en 0.0 (tarea de
           clasificacion binaria, no necesita creatividad). Reverificado
           con texto fijo: 5/5 llamadas identicas con el MISMO modelo
           (minimax-m3) dieron el MISMO veredicto -- el clasificador ya es
           determinista por input. La unica vez que cambio en una prueba de
           6 llamadas fue cuando minimax-m3 fallo (inestabilidad real de
           NVIDIA NIM, confirmada en vivo varias veces en esta sesion) y el
           fallback cayo a deepseek-v4-pro, que dio un veredicto DISTINTO
           sobre el MISMO texto -- desacuerdo real entre modelos en un caso
           limite, no ruido del clasificador en si.
        2. Pipeline COMPLETO (generacion + clasificador) corrido 4 veces
           seguidas para la misma pregunta: **3/4 grounded=False, 1/4
           grounded=True**. En 3 de las 4 corridas el modelo de generacion
           fue el MISMO (minimax-m3) pero el texto generado vario lo
           suficiente (temperature=0.1 en la generacion principal, a
           proposito, para prosa natural -- no se toca) para que el
           clasificador, ya determinista por input, diera veredictos
           correctamente distintos sobre esos inputs genuinamente
           distintos.
      - **Conclusion honesta**: la varianza real de este test viene de que
        Ley de Salud Art.228/230 esta en la frontera semantica de "mismo
        tema" (control antirrabico) vs. "tema distinto" (maltrato/
        bienestar animal) -- pequenas variaciones en como el LLM principal
        redacta la respuesta empujan el juicio para un lado u otro. El fix
        de `temperature=0.0` es una mejora real y verificada (elimino el
        ruido del clasificador en si), pero NO elimina esta flakiness
        especifica porque su fuente real esta aguas arriba, en la
        generacion principal. Convertido a `pytest.xfail()` (mismo patron
        que el caso de tortura), con el docstring del test actualizado para
        documentar el diagnostico preciso -- no se ajusta mas el prompt del
        clasificador para "ganarle" a este caso especifico
      - **Nota metodologica mas amplia que esto destapo**: dado que la
        generacion principal corre con temperature=0.1, cualquier corrida
        unica del golden dataset trae algo de ruido de muestreo genuino en
        los tests que dependen de texto generado (no en los que se
        verificaron con `dense_search`/`hybrid_search` directos y
        deterministas, como el fix de `k` y la expansion de sinonimos
        legales, documentados arriba). Los deltas 17/2/5 -> 19/2/3 -> 21/2/1
        de esta fase reflejan efectos reales de codigo (cada uno verificado
        ademas con evidencia directa, no solo el conteo agregado), pero no
        deben leerse como medidas de precision absoluta -- una sola corrida
        de 24 preguntas no es un benchmark estadisticamente estable para
        los casos limite
        `[Yo directamente, con pruebas aisladas de determinismo del
        clasificador (texto fijo, temperature 0.1 vs 0.0) y 4 corridas
        reales del pipeline completo antes de aceptar cualquier
        conclusion]`
- [x] **Clasificador de grounding, 2 mejoras reales tras revisar el
      diagnostico de no-determinismo entre proveedores** — el usuario
      propuso 3 opciones para cerrar la brecha de desacuerdo minimax-m3 vs.
      deepseek-v4-pro (ver hallazgo arriba), evaluadas asi:
      1. **Pasar los chunks reales al clasificador** (implementada) --
         antes `answer_is_grounded_in_practice(question, answer_text)`
         solo veia la respuesta final, un juicio abierto de "tono" donde
         cada proveedor trae su propio criterio no calibrado. Ahora recibe
         tambien `retrieved_chunks` (los MISMOS que uso el LLM principal) y
         la pregunta se vuelve mecanica: "¿esta respuesta usa contenido de
         ESTOS pasajes, o los ignora?"
      2. **5 ejemplos fijos (few-shot) anclando el criterio** (implementada)
         -- los 6 casos verificados a mano en esta sesion menos
         `proteccion_animal` (deliberadamente excluido: ese caso quedo
         documentado como ambiguedad LEGITIMA entre modelos, no un error;
         anclarlo con un veredicto fijo forzaria una respuesta unica a algo
         que se decidio explicitamente no forzar)
      3. **found_answer autodeclarado en la misma llamada de generacion**
         (NO implementada, deferida) -- razonamiento del usuario mejor que
         el original (no era un problema de latencia, era que un auditor
         EXTERNO puede discrepar de la intencion del generador aunque el
         generador mismo hubiera estado seguro), pero la pregunta que el
         propio usuario marco como la correcta a validar primero (structured
         output confiable en los 5 proveedores del fallback) sigue sin
         responder, y tocaria el camino de generacion PRINCIPAL, no un gate
         auxiliar. Se decide medir 1+2 primero (mas barato, mas acotado) y
         solo evaluar 3 si sigue haciendo falta
      - `app/rag/grounding.py`: `_FEW_SHOT_EXAMPLES` (5 casos reales,
        excertps recortados), `_build_messages()` arma el prompt como
        pares user/assistant de ejemplo + el caso real al final;
        `answer_is_grounded_in_practice()` ahora acepta
        `retrieved_chunks: list[RetrievedChunk] | None` y devuelve
        `(veredicto, proveedor_usado)` en vez de solo el booleano
      - **Extra barato pedido por el usuario, independiente de cual opcion
        se eligiera**: persistir que proveedor respondio cada llamada del
        clasificador. Nuevo campo `ChatResponse.grounding_classifier_model`
        y columna `Message.grounding_classifier_model` (migracion manual
        `ALTER TABLE`, mismo patron que `error_message`) -- para poder
        diagnosticar un desacuerdo futuro sin re-investigar desde cero
        (distinguir "cambio de proveedor" vs. "el mismo proveedor discrepo
        consigo mismo")
      - **MEDIDO contra el golden dataset completo**, `pytest
        tests/test_rag_regression.py -v -s`, 24 preguntas, sin mocks,
        737.40s = 12m17s (mas lento por el prompt few-shot mas largo, 5
        ejemplos completos en cada llamada del clasificador): **22 passed,
        2 xfailed, 0 failed** -- CERO fallas duras, mejor resultado de toda
        la fase (antes: 21/2/1). `test_no_encontrado_proteccion_animal`
        (el caso documentado como ambiguo) paso limpio esta vez con
        `grounded=False`; los 2 xfailed restantes son los ya conocidos y
        sin relacion con el clasificador (tortura: umbral de similitud;
        sucesion Art.1576: calidad de embedding, fix caro diferido) --
        confirma que 1+2 fueron suficientes, no hizo falta la opcion 3
        `[Yo directamente, con verificacion end-to-end antes de medir:
        import/construccion de mensajes, poblacion real del campo nuevo en
        una corrida individual, y solo despues la corrida completa]`
- [x] **Hallazgo real urgente, fuera del alcance de ambos documentos, ya
      RESUELTO** — `sparse_search` (BM25) reconstruia el indice completo
      desde cero EN CADA pregunta, sin cache. Arreglado en
      `app/rag/retriever.py`: cache en memoria a nivel de modulo
      (`_bm25_cache`), invalidado por una firma barata
      (`_corpus_signature()` = `COUNT(*)` + `MAX(id)` de chunks activos,
      una query indexada) en vez de un TTL a ciegas -- se reconstruye SOLO
      cuando el corpus de verdad cambio (ley nueva ingerida, o un documento
      activado/desactivado como el duplicado de Hacienda Publica), no en
      cada pregunta. Funciona incluso si el cambio vino de OTRO proceso
      (ej. un script `load_*.py` corriendo aparte) porque siempre compara
      contra el estado real de la DB, nunca confia solo en memoria.
      Medido en vivo contra la DB real (7746 chunks, 17 leyes activas):
      primera llamada (construye indice) ~6.2s, llamadas siguientes con
      cache valido **~0.05s (~100x mas rapido)**. Verificada la
      invalidacion de verdad: desactivar la Ley de Bibliotecas cambio la
      firma de `(6757, 7755)` a `(6714, 7755)` (diferencia de 43, exacto el
      numero de chunks de esa ley) y disparo una reconstruccion real; al
      reactivarla, la firma volvio a `(6757, 7755)` y reconstruyo de nuevo.
      `pytest tests/test_chunker.py tests/test_guardrails.py` 20/20 sin
      regresion. Hecho por mi directamente, sin subagente
- [x] **Cache semantico** — implementado siguiendo
      `LexChiapas_Reranker_y_Cache_Semantico.md` seccion 2, con la
      alternativa MVP explicitamente sancionada ahi (invalidacion por TTL
      simple, no por documento re-ingerido -- evita tener que rastrear
      `source_document_ids` y tocar `RetrievedChunk`/`dense_search` para
      exponer `document_id`).
      - `app/models/semantic_cache.py` (nuevo): `SemanticCacheEntry`
        (`question_text`, `question_embedding vector(1024)`,
        `response_json JSONB`, `hit_count`, `created_at`, `last_used_at`),
        mismo patron ORM que `Chunk`/`Message`. Tabla creada en la DB real
        via `CREATE TABLE IF NOT EXISTS` directo (sin alembic, igual que
        cambios de esquema anteriores de esta sesion)
      - `app/rag/semantic_cache.py` (nuevo): `lookup()`/`store()`.
        `lookup()` usa SQL crudo con `<=>` de pgvector (mismo estilo que
        `dense_search`, no el comparador ORM de pgvector, por consistencia
        con el resto del codebase) filtrado por TTL y ordenado por
        similitud; `store()` usa el ORM directo (mismo patron que
        `embed_and_store_chunks` en `app/rag/embeddings.py`, que ya prueba
        que pgvector.sqlalchemy.Vector serializa listas de Python sin SQL
        crudo)
      - `app/rag/retriever.py`: `_to_vector_literal` renombrada a
        `to_vector_literal` (publica) para reusarla en `semantic_cache.py`
        sin duplicar el helper
      - `ai_config.json` `semantic_cache`: `similarity_threshold=0.97`
        (extremo conservador del rango 0.95-0.97 sugerido por el
        documento fuente -- un falso positivo aqui devuelve la respuesta
        COMPLETA de una pregunta distinta, mucho mas grave que un chunk de
        mas en retrieval normal), `ttl_days=30`, `enabled=true`
      - **Decision de diseño no cubierta por el documento fuente** (escrito
        antes de Fase 2.6/memoria conversacional): el cache SOLO se usa
        para preguntas SIN `conversation_history` (`app/rag/
        rag_pipeline.py`). Una pregunta corta de seguimiento ("Y las
        multas?") depende del contexto de ESA conversacion en particular
        -- cachearla por similitud de embedding sola reutilizaria una
        respuesta de un contexto de conversacion distinto sin darse
        cuenta. Confirmado que esto SI se activa en produccion real (no
        solo en pruebas aisladas): `get_recent_history` devuelve `[]` en el
        primer turno de cualquier conversacion nueva (Telegram/web), asi
        que el primer turno de cada conversacion es cacheable y los
        seguimientos no, sin necesidad de tocar `conversation_store.py`.
        **No es una restriccion permanente por diseño, es una restriccion
        NECESARIA con el diseño actual** (el cache solo sabe embeber la
        pregunta sola, no puede representar con seguridad "esta pregunta
        corta EN EL CONTEXTO de esta conversacion especifica"). Se podria
        extender mas adelante (ej. embeber pregunta+historial reciente en
        vez de la pregunta sola) si la memoria conversacional crece y
        conviene cachear seguimientos tambien -- pero el impacto real de
        esta restriccion en la tasa de aciertos es una pregunta EMPIRICA
        pendiente, no una suposicion: si la mayoria de los usuarios de
        Telegram hacen una pregunta y no continuan la conversacion (patron
        plausible para un bot de consulta legal puntual), casi todo el
        trafico real ya es "primer turno" y esta restriccion apenas reduce
        el hit rate practico. Se debe medir con datos reales de produccion
        (via `cache_hit_rate`, pendiente en el dashboard, ver abajo) antes
        de decidir si vale la pena la complejidad de extenderlo
      - **¿Se cachea tambien `grounded: False`?** Si, decision explicita
        (no un vacio sin resolver): `cache_store()` se llama
        incondicionalmente al final del pipeline para preguntas sin
        historial, sin filtrar por `response.grounded` -- una pregunta
        legitimamente fuera del corpus (ej. "ley de proteccion al
        consumidor") tambien cuesta un `hybrid_search`+rerank completo cada
        vez que se repite, aunque no llegue a llamar al LLM principal (ver
        `generate_answer`, que corta antes del LLM si no hay chunks). Las
        preguntas rechazadas por Capa 1 (guardrails, fuera de dominio total)
        NUNCA llegan a este punto -- ya son baratas de por si, no vale la
        pena cachearlas
      - **Riesgo real de obsolescencia, identificado por el usuario y
        CORREGIDO (no solo documentado)**: el umbral de similitud (0.97)
        protege contra devolver la respuesta de una ley EQUIVOCADA, pero no
        dice nada sobre si una respuesta correcta-en-su-momento sigue
        vigente -- un TTL ciego de 30 dias podria servir una version
        obsoleta de la ley correcta si esta se re-ingirio (deactivate+
        insert, el patron ya establecido en este proyecto) minutos despues
        de cachear la respuesta. Arreglado reusando el MISMO mecanismo ya
        verificado del cache de BM25 (`app.rag.retriever.corpus_signature`,
        renombrada de privada a publica): cada entrada de `semantic_cache`
        guarda la firma del corpus (`corpus_chunk_count`,
        `corpus_max_chunk_id`) al momento de crearse, y un hit exige que la
        firma ACTUAL coincida exacto -- el TTL de 30 dias queda como
        limpieza secundaria de espacio, no como el mecanismo principal de
        invalidacion. **Verificado en vivo** (mismo estilo de prueba que la
        verificacion del cache de BM25): pregunta cacheada -> segunda
        corrida da HIT real -> se desactiva temporalmente un documento
        cualquiera (simulando un cambio real de corpus) -> tercera corrida
        de la MISMA pregunta ignora la entrada vieja y corre el pipeline
        completo de nuevo -> documento reactivado, estado de la DB
        restaurado
      - **Bug real encontrado y corregido durante la implementacion**:
        `query_embedding` se reasigna mas abajo en `rag_pipeline.py` si
        `expand_legal_synonyms` modifica la consulta de busqueda -- sin
        capturar `original_query_embedding` por separado ANTES de esa
        reasignacion, `cache_store()` habria guardado bajo un embedding
        distinto al que uso `cache_lookup()`, rompiendo la simetria
        lookup/store para cualquier pregunta que matched un patron de
        `app.rag.legal_synonyms`
      - **Bug real encontrado y corregido en el propio golden dataset**:
        las 24 preguntas de `tests/test_rag_regression.py` se llaman SIN
        `conversation_history`, asi que TODAS pasan por el cache. Sin
        limpiarlo, una segunda corrida del archivo despues de un cambio de
        codigo real (retriever/reranker/grounding) habria devuelto
        respuestas CACHEADAS de la corrida anterior en vez de ejercitar el
        pipeline real -- exactamente lo que este set de regresion existe
        para evitar. Arreglado con un `TRUNCATE TABLE semantic_cache` en el
        fixture `db` (scope=module, una vez por corrida completa del
        archivo)
      - **MEDIDO end-to-end contra la DB/API real** (no solo leido el
        codigo): misma pregunta 2 veces -- corrida 1 (miss real) 32.33s,
        corrida 2 (hit real) 0.45s, **~70x mas rapido**, respuesta
        identica byte a byte. Probada una pregunta parafraseada
        (`"Cuantos dias de vacaciones le dan a los empleados..."` vs.
        `"...tienen los trabajadores..."`): similitud real medida 0.9499,
        POR DEBAJO del threshold 0.97 -- no dio hit, se inserto como
        entrada nueva. Dato de calibracion real para referencia futura: un
        parafraseo genuino y cercano en espanol legal puede caer en el
        rango 0.94-0.96, incluso por debajo del extremo mas permisivo
        sugerido por el documento fuente (0.95) -- confirma que el umbral
        conservador SI sacrifica algunos hits legitimos a cambio de cero
        riesgo de devolver la ley equivocada, tal como el documento fuente
        preveia explicitamente
        `[Yo directamente, con verificacion end-to-end real de miss/hit/
        parafraseo/hit_count contra la DB real antes de dar esto por
        terminado]`
- [x] **Auditoria de seguridad de contenido scrapeado** — el documento
      fuente pedia verificar si existe un agente `security-guardian` y
      crearlo si no. Confirmado: NO existe (ni proyecto ni global). Pero el
      agente `security` que SI existe (`.claude/agents/security.md`) ya
      cubre este escenario exacto en su item 4 ("Prompt injection via
      retrieved/ingested content..."). Decision: NO crear un agente nuevo
      (violaria la preferencia explicita del usuario de mantener solo 5
      subagentes lean, dada al inicio del proyecto) -- usar `security`
      cuando se corra la auditoria real, todavia pendiente de ejecutar
      (esto solo resuelve el meta-punto de que agente usar, no la
      auditoria en si)

---

## Fase 4 — Celery + ingesta automatica (COMPLETADA)

Objetivo del brief: sistema que se actualiza solo.

- [x] Levantar Redis y confirmar que `celery -A app.workers.celery_app worker`
      y `celery ... beat` corren sin error `[Subagente: bugs]` si truena --
      **si truena, hallazgo real**: el `redis-server` local de este
      proyecto es 5.0.14 (verificado con `INFO server`, un puerto viejo de
      Redis para Windows). `redis-py` 6+ (se habia instalado 8.0.1, porque
      `requirements.txt` solo fijaba `redis>=5.0` sin techo) intenta
      negociar RESP3 por defecto (comando `HELLO` al conectar), que Redis
      5.0.14 rechaza con "unknown command HELLO". `app/rag/memory.py` YA
      resolvia esto para el uso directo del cliente (`protocol=2`
      explicito), pero Celery segui fallando: `celery -A ... worker` se
      quedaba reintentando indefinidamente ("Cannot connect to
      redis://localhost:6379/0: unknown command HELLO"), porque `kombu`
      (el transporte de Celery) construye `redis.Connection` DIRECTO via
      un connection pool, y `protocol` no esta en la lista blanca
      `Channel.from_transport_options` de kombu -- no hay forma de pasarlo
      via `broker_transport_options`. Ademas, `redis-py` 6+ agrega una
      funcion nueva ("maintenance notifications", para Redis Enterprise)
      que truena con OTRO error distinto especificamente en el camino de
      kombu, incluso forzando protocol=2 a mano.
      - Arreglado en dos partes: (1) `requirements.txt` fija
        `redis>=5.0,<6.0` (la generacion 5.x no tiene la funcion de
        maintenance notifications, funciona limpio con ambos usos), (2)
        `app/workers/celery_app.py` registra una subclase minima
        `_Resp2Connection(redis.Connection)` que fuerza `protocol=2` si no
        se especifica, como `connection_class` del canal de kombu, ANTES
        de construir la app de Celery
      - **Verificado en vivo, no solo la teoria**: `celery -A
        app.workers.celery_app worker --loglevel=info -P solo` ->
        "Connected to redis://localhost:6379/0" (antes: reintentos
        indefinidos). `celery -A app.workers.celery_app beat
        --loglevel=info` -> arranca sin error. Sin procesos huerfanos
        despues de las pruebas (confirmado con `tasklist`)
        `[Yo directamente, diagnostico y fix con verificacion en vivo del
        worker y el beat reales, no solo una conexion de prueba aislada]`
- [x] Implementar de verdad `check_for_law_updates` (hoy es un placeholder
      que devuelve `{"checked": 0, "updated": 0}`): comparar
      `fecha_ultima_reforma` contra la fuente y disparar `ingest_document`
      si cambio `[Subagente: data-extraction]` + `[Subagente: logic]` --
      **`fecha_ultima_reforma` no se llena de forma confiable hoy, no sirve
      como señal**. Señal real usada: comparar `Document.source_url`
      guardado contra el que devuelve HOY el scraper de la MISMA fuente
      (Congreso o Consejeria, nunca cruzado -- dominios distintos por
      diseño) para esa ley por nombre normalizado (mismo patron de
      matching ya verificado con el scraper de Congreso). Match ambiguo
      (mas de una ley matchea) se descarta -- mismo criterio de precaucion
      que el incidente real Fiscal/Hacienda.
      - **Bug real corregido primero**: `ingest_document` SOLO agregaba
        chunks, nunca borraba los viejos -- reingerir un documento ya
        cargado habria dejado chunks VIEJOS y NUEVOS coexistiendo en la
        misma busqueda. Agregado `replace_existing: bool = False`
        (default preserva el comportamiento de los `load_*.py`
        existentes); cuando es `True`, borra los chunks del document_id
        ANTES de insertar los nuevos
      - **Segundo bug real encontrado durante la verificacion (no en
        teoria)**: la primera corrida real marco los 9 documentos activos
        de Consejeria como "candidatos a reforma" -- falso positivo
        generalizado. Causa: `consejeria_scraper.list_available_laws()`
        devuelve el href CRUDO del HTML (dominio viejo, sin url-encodear),
        mientras que los `source_url` ya guardados usan el dominio que
        realmente sirve el archivo, url-encodeado (ver
        `consejeria_scraper.py`). Arreglado con
        `_normalize_url_for_comparison` (decodifica y homologa host SOLO
        para decidir si cambio, no toca el valor real que se descarga o
        persiste)
      - Un fallo en un documento (descarga/parsing/embeddings) se registra
        en `errors` y NO detiene el chequeo del resto; sin commit parcial
        (rollback) para no dejar `source_url` apuntando a contenido que no
        se termino de reingerir
      - **MEDIDO/verificado en vivo, dos veces (por el agente y por mi de
        forma independiente)**: `replace_existing=True` probado en
        aislado sobre Ley de Amnistia (doc 4) -- reingerida 2 veces con el
        mismo texto fuente, chunks se mantuvo en 7 ambas veces (sin
        duplicar), `source_url`/`is_active` intactos (confirmado
        directamente contra la DB real). `check_for_law_updates()`
        corrido de verdad contra el estado actual (19 documentos, 18
        activos, 8547 chunks): **`{'checked': 18, 'updated': 0,
        'updated_documents': [], 'errors': []}`** -- reproducido
        exactamente igual en mi propia corrida independiente. Cero
        candidatos reales de reforma hoy (esperado, el corpus se cargo
        hace poco). `pytest tests/test_chunker.py tests/test_guardrails.py`
        -- 21/21 (verificado por mi tambien)
        `[Subagente: logic], verificado independientemente por mi
        (conteos directos contra la DB, re-corrida de check_for_law_updates,
        y los 21 tests rapidos)`
- [x] Panel admin: probar `POST/GET/DELETE /admin/documents` con la
      `ADMIN_API_KEY` real, confirmar que sin la key da 401
      `[Subagente: security]` -- **sin vulnerabilidades de bypass reales,
      verificado independientemente**:
      - Sin autenticacion: 401 limpio en los 4 endpoints probados
        (GET/POST/DELETE `/admin/documents` + `/admin/metrics/usage`),
        reconfirmado en vivo por mi tambien
      - Login: key incorrecta -> 401; key real -> 200 + cookie de sesion
        (`httponly`, `samesite=lax`)
      - CRUD con sesion valida: GET/POST/DELETE funcionan como se espera
        (`DELETE` hace soft-delete, `is_active=False`, comportamiento
        correcto). Documento de prueba creado y borrado por completo al
        terminar -- confirmado 0 restantes y el conteo total de vuelta a
        19 documentos
      - **Cookie de sesion revisada con ojo de seguridad, no solo "existe"**:
        `app/api/admin_auth.py` usa HMAC-SHA256 sobre un timestamp,
        comparacion timing-safe (`hmac.compare_digest`), TTL de 24h
        validado server-side -- confirmado leyendo el codigo Y probando
        manipulacion directa de la cookie (firma alterada, valor
        inventado, formato invalido) -- los 3 casos dieron 401,
        reconfirmado en vivo por mi con una cookie manipulada aparte. No
        es forjable sin la `signing_key`
      - **Hallazgo real, no corregido a proposito**: `/admin/login` NO
        tiene rate-limiting (`app/api/rate_limit.py` existe pero no esta
        importado en `admin.py`, confirmado por grep) -- 15 intentos
        seguidos con key incorrecta dieron 401 sin ningun 429. No es un
        bypass de autenticacion (la key real sigue siendo necesaria), es
        ausencia de mitigacion de fuerza bruta contra una API key
        compartida de 13 caracteres -- queda documentado como decision
        pendiente, no arreglado sin confirmacion explicita (mismo criterio
        que el resto de la sesion: no tocar mas alla de lo pedido sin
        avisar)
        `[Subagente: security], verificado independientemente por mi
        (lectura de admin_auth.py, prueba en vivo de 401 sin auth y con
        cookie manipulada, confirmacion de que no quedo basura en
        documents)`
- [x] Sistema de feedback: agregar el endpoint que falta para que un
      usuario marque una respuesta como util/no_util (hoy el modelo
      `Feedback` existe pero no hay endpoint) `[Subagente: logic]` --
      **checklist desactualizado**: el endpoint YA existia
      (`app/api/feedback.py`, `POST /api/feedback`) y ya estaba registrado
      en `main.py` (`app.include_router(feedback.router)`) -- de una pasada
      anterior del scaffold, nunca antes verificado contra un servidor
      real. Verificado ahora en vivo (`uvicorn` real, no mocks): 404 para
      `message_id` inexistente, 422 para `rating` invalido, 200 con
      insercion real para un `message_id` real -- los 3 casos con status
      code correcto. Fila de prueba limpiada despues. Servidor y proceso
      cerrados al terminar `[Yo directamente, con servidor real levantado
      y 3 casos probados con curl]`
- [x] Revisar `ingestion_logs` despues de varias corridas: que capture
      errores reales de forma util para debug `[Subagente: bugs]` --
      **hallazgo real**: `ingestion_tasks.py` guardaba `str(exc)` en
      `error_message`, que solo captura el mensaje final, no archivo/linea
      de donde trueno -- insuficiente para debuggear un fallo real de
      chunking/embedding a mitad de un documento largo sin reproducirlo a
      mano. Arreglado con el mismo patron ya establecido para
      `Message.error_message` (Fase 3.7): `traceback.format_exception(exc)`
      completo, truncado a 4000 caracteres. **Verificado con una excepcion
      real forzada** (no solo leido el codigo): `ingest_document(document_id=24,
      raw_text=123)` (tipo invalido a proposito, falla en
      `chunk_legal_text` ANTES de tocar embeddings/chunks reales del
      documento 24) -- `error_message` capturo el traceback completo con
      archivo y linea exactos (`chunker.py:305`). Fila de prueba limpiada
      despues `[Yo directamente, con una falla real forzada contra la DB
      real]`

**Entregable:** ingesta y actualizacion de leyes corriendo en background sin
intervencion manual.

---

## Fase 5 — WhatsApp + pulido

Objetivo del brief: segundo canal y experiencia completa, listo para
portafolio.

- [x] ~~Implementar `WhatsAppBot`~~ **DECISION: no se implementa, a
      proposito** -- discutido con el usuario: motivacion real era mostrar
      soporte multicanal para reclutadores, no demanda real de usuarios.
      Ni Baileys ni OpenWA tienen API oficial gratuita -- ambos requieren
      un proceso Node.js aparte y vincular un numero de telefono real por
      QR, con riesgo real de baneo por automatizacion si corre 24/7.
      Costo/riesgo operativo no justificado sin demanda real. La
      arquitectura SI queda lista para esto (`app/bots/base_bot.py` ya
      diseñada desde el inicio como interfaz comun multicanal,
      `telegram_bot.py` es la unica implementacion concreta) -- eso ya es
      la señal de arquitectura que un recruiter puede ver en el codigo,
      sin necesitar el canal en vivo. Documentado en `README.md`. Revisar
      si en el futuro hay demanda real de usuarios de Chiapas pidiendo
      WhatsApp especificamente -- ahi si justificaria el costo
- [ ] ~~Implementar `app/api/whatsapp_webhook.py` de verdad~~ -- depende del
      item anterior, no aplica mientras no se decida implementar WhatsApp
- [ ] Metricas basicas de uso (preguntas mas comunes, ratio util/no_util)
- [ ] README profesional con demo/GIF, `CLAUDE.md` actualizado si cambio
      algo de la arquitectura
- [ ] Deploy 24/7 (revisar manejo de secretos en el entorno de deploy)
      `[Subagente: security]`

**Entregable:** LexChiapas en Telegram y WhatsApp, listo para mostrar.

---

## Fase 6 — RAG Avanzado (Nivel 2)

Documento fuente completo: **`LexChiapas_Evolucion_RAG_Progresiva.md`** (raiz
del repo) — leerlo para el detalle tecnico completo de cada tecnica. Este
documento y sus 3 fases (RAG Avanzado -> Agentic RAG -> GraphRAG) equivalen a
los "Nivel 2 -> Nivel 3 -> Nivel 4" que `WEB_FRONTEND_PLAN.md` ya menciona
como progresion futura ("seguimos en Nivel 1"). Aqui es donde esa progresion
se vuelve un plan activo con checklist, ya no solo una idea compartida.

**Punto de partida que este documento asume ya resuelto** (verificar antes de
empezar, no asumir): chunking legal, embeddings, pgvector, hybrid search,
threshold, reranking, grounding, citas, guardrails (Fase 2.5) y bot de
Telegram (Fase 3). Si alguna de esas fases sigue incompleta, resolverla
primero — el documento fuente es explicito: **"Cada fase debe funcionar por
si sola antes de pasar a la siguiente. Sin prisa"** y **"son necesidades, no
especificaciones rigidas"**.

**Nota — mejoras RAG condicionadas (`LexChiapas_Formato_y_Mejoras_Futuras.md`
Parte 2):** ese documento agrega 3 refinamientos que NO se implementan ahora
ni tienen checklist activo aqui, se evaluan despues de que esta fase (y
Fase 7-8) den buenos resultados, usando el dashboard de metricas del frontend
para decidir si valen la pena:
- Parent-child retrieval (buscar con chunks chicos, responder con el
  articulo/seccion completa como contexto) — si se nota que las respuestas
  citan fragmentos sueltos sin contexto.
- Reranking real con cross-encoder o LLM-as-judge (mejora del reranking
  basico ya contemplado en Fase 2) — si el reranking actual deja fuera del
  top chunks que si eran relevantes.
- Correccion ortografica de la pregunta antes de re-escribirla (variante del
  query rewriting de esta fase) — si usuarios reales escriben con muchos
  errores y eso degrada la busqueda.

No sobre-ingenierizar: el documento fuente es explicito en que estas 3 solo
se agregan si los datos reales del dashboard muestran que hacen falta, el
proyecto ya esta solido sin ellas — revisar el codigo real de `app/rag/`
antes de implementar cada tecnica, no copiar literal.

Sigue siendo un pipeline lineal (a diferencia de Fase 7), pero mucho mas
inteligente en como recupera.

**Checklist (basado en las secciones 1.1-1.4 del documento fuente):**

- [x] **Query rewriting — COMPLETADO (2026-07-10), cierra el gap dejado
      pendiente en Fase 2.6.** Archivo nuevo `app/rag/query_rewriting.py`,
      `rewrite_query(question, conversation_history)`.
      - **Modelo elegido:** `mistralai/ministral-14b-instruct-2512` (via
        NVIDIA NIM), verificado con llamadas reales antes de comprometerse
        (misma disciplina de siempre). Se probaron 2 alternativas mas
        chicas primero: `meta/llama-3.2-3b-instruct` colgo dos veces
        seguidas (timeout de 60-120s, mismo patron de latencia intermitente
        de NVIDIA NIM ya documentado en Fase 2.5/2.6);
        `nvidia/nemotron-mini-4b-instruct` respondio rapido pero SOLO en
        ingles pese al prompt en espanol -- inservible para reescribir a
        espanol legal. Ministral-14b entiende bien el registro legal en
        espanol; el primer intento con un prompt de una linea devolvia
        respuestas largas tipo "consulta legal formal" en vez de una
        pregunta corta -- se agrego un ejemplo few-shot en el system prompt
        para forzar formato breve de una sola linea.
      - **Heuristica de cuando reescribir** (`needs_rewriting()`): solo si
        hay `conversation_history` (sin historial no hay nada que
        contextualizar) Y la pregunta tiene 6 palabras o menos (senal
        barata, sin API, de que probablemente depende de contexto previo).
        Evita gastar una llamada de mas en preguntas ya auto-contenidas.
      - **Que se reescribe y que no:** solo el texto usado para
        `embed_text()`/`hybrid_search()`/`rerank()` (retrieval). La
        pregunta que ve el LLM en la generacion final
        (`generate_answer()`/`build_prompt()`) sigue siendo la ORIGINAL del
        usuario, no la reescrita — la reescritura es una ayuda de busqueda,
        no debe cambiar como el bot le habla al usuario. Capa 1 (guardrails)
        tambien sigue operando sobre la pregunta ORIGINAL, antes de
        cualquier reescritura, para mantenerse como el filtro mas barato
        (ya maneja razonablemente bien seguimientos cortos via su fallback
        de keywords, no necesitaba esperar a la reescritura).
      - **"Guardar tanto la pregunta original como la reescrita"** (pedido
        explicito del checklist original): se hace via `logger.info()` en
        `query_rewriting.py` (modulo `lexchiapas.query_rewriting`), NO como
        columna nueva en `messages` — se evito tocar ese modelo compartido
        porque otra sesion en paralelo ya le esta agregando columnas para
        el dashboard de metricas de `WEB_FRONTEND_PLAN.md`; agregar la
        reescritura al log de logging es suficiente para inspeccionar/
        auditar sin arriesgar un choque de ediciones.
      - **Fallo seguro:** si la llamada al modelo de reescritura falla o
        tarda, `rewrite_query()` devuelve la pregunta original sin cambios
        — un componente auxiliar lento no debe tumbar el pipeline principal
        (mismo principio que el timeout de 60s de Fase 2 en
        `app/llm/providers.py`).
      - **Verificado con el caso EXACTO que fallo en Fase 2.6:**
        conversacion de 2 turnos sobre la Ley de Tortura ("Que se considera
        tortura...?" seguido de "Y que sanciones tiene?"). Antes de esta
        fase, el Turno 2 daba `grounded: False` (similitud maxima 0.385,
        por debajo del threshold 0.5). **Con query rewriting, el mismo
        Turno 2 ahora da `grounded: True`**, citando correctamente
        Articulo 3 y Articulo 5 de la Ley de Tortura, con similitudes
        0.565-0.596 (los 3 chunks del top-3 son de la ley correcta). El
        gap que Fase 2.6 dejo documentado como limite conocido queda
        cerrado. `[Subagente: logic]`
- [x] **HyDE (Hypothetical Document Embeddings)** — implementado y medido,
      **`hyde.enabled=true`**. `app/rag/hyde.py`
      `generate_hypothetical_answer(question)` usa `generate_with_fallback`
      (mismo router multi-proveedor del resto del pipeline) para generar
      un fragmento legal hipotetico corto; si falla, `None` (fallback
      seguro, sigue con el embedding directo). Integrado en
      `rag_pipeline.py` DESPUES de query rewriting + expansion de
      sinonimos legales (se beneficia de ambos), reemplaza SOLO el
      `query_embedding` de `dense_search` -- el `query_text` de BM25/
      `sparse_search` sigue siendo la pregunta real, nunca el texto
      generado (evita diluir la precision lexica de BM25). Bandera en
      `ai_config.json` (`hyde.enabled`) para medir con/sin sin tocar
      codigo.
      - **Proceso de medicion con problemas reales de infraestructura,
        documentados con honestidad**: intentar correr las 24 preguntas
        completas en una sola pasada fallo repetidas veces por causas
        AJENAS al codigo -- degradacion real de NVIDIA (preguntas
        tardando 100-400s en vez de los 12-13s normales, ya visto antes
        en la sesion) combinada con procesos en segundo plano que se
        cortaban sin terminar (tanto los del subagente delegado como mis
        propios monitores). El subagente asignado a esta tarea quedo
        varias veces atascado esperando notificaciones de sus propios
        procesos en background sin progresar; se le reasumio manualmente
        mas de una vez, y finalmente se corrigio corriendo la medicion
        directamente en vez de seguir delegandola
      - **Verificacion final NO basada solo en el autoreporte del agente**
        (su primer resumen de "24/24 completo" no coincidia con lo que se
        veia en el log real en ese momento): se reconstruyo el resultado
        leyendo el log crudo directamente -- 20 de 21 preguntas de una
        corrida continua real dieron resultado (19 passed + 1 xfail,
        `test_derechos_humanos_tortura_sanciones_limite_conocido`, ambos
        consistentes con lo esperado), mas una corrida chica aparte
        (86.18s, sin problemas) para las 4 preguntas faltantes
        (`test_no_encontrado_proteccion_animal` + las 3 de fuera de
        dominio) -- total real armado con evidencia directa: **22 passed,
        2 xfailed, 0 failed**, exactamente el mejor resultado ya medido en
        la sesion, PERO con una mejora real nueva:
      - **`test_civil_sucesion_intestada_limitacion_conocida` (Art.1576,
        "quien hereda sin testamento") paso de XFAIL a PASSED** --
        verificado leyendo el log crudo directamente, no el resumen del
        agente: Art.1576 aparecio en la posicion 1 (similitud 0.669),
        `grounded=True`, cita correcta. Este es el mismo caso que se
        investigo exhaustivamente en Fase 3.7 (posicion #233 de 6757 con
        la mejor expansion de consulta barata posible, luego el
        experimento de contexto de Titulo/Capitulo tambien fallido, ver
        arriba) -- HyDE SI logra lo que ninguna de las otras dos vias
        pudo: la respuesta hipotetica generada por el LLM aparentemente
        usa vocabulario legal ("sucesion legitima", "tienen derecho a
        heredar") mas cercano al chunk real que la pregunta coloquial
        original, incluso despues de la expansion de sinonimos
      - **Hallazgo lateral, no relacionado con HyDE**: en la corrida
        chica final, `test_no_encontrado_proteccion_animal` encontro
        `Codigo Penal para el Estado de Chiapas Art.495` -- un articulo
        REAL y dedicado a "maltrato o crueldad contra animales de
        compania" (agregado con el Codigo Penal en Fase 4, no existia
        cuando se escribio este test). La ambiguedad documentada antes
        (Ley de Salud, control antirrabico vs. maltrato) puede ya no
        aplicar -- el corpus ahora SI tiene una disposicion dedicada al
        maltrato animal. Posible candidato a actualizar este test (mismo
        tratamiento que se le dio a `test_no_encontrado_codigo_penal`
        cuando se cargo esa ley) -- no se toco todavia, queda anotado
      - **Costo real documentado, no ignorado**: HyDE agrega una llamada
        LLM extra ANTES de cada busqueda. Caso concreto observado
        (`test_no_encontrado_ley_federal_trabajo`): sin HyDE resuelve en
        ~1.2s (nada cruza threshold, ni siquiera se llama al LLM
        principal); con HyDE, la respuesta hipotetica acerco chunks lo
        suficiente para disparar una generacion completa (~218s) que el
        segundo gate de grounding igual degrado correctamente a False --
        mismo resultado final, mas costo. Tradeoff real, aceptado dado el
        beneficio verificado en Art.1576
        `[Subagente: logic] + verificado independientemente por mi
        (lectura directa de logs crudos, no el resumen del agente;
        corrida propia de las 4 preguntas faltantes)`
      - **Seguimiento del usuario: medir el costo sistematicamente, no solo
        el caso de ley_federal_trabajo, y evaluar un pre-check barato antes
        de pagar HyDE** (correr `dense_search` normal primero -- ya se hace
        de todas formas -- y saltar HyDE si el mejor resultado esta muy por
        debajo del threshold, mismo patron que `needs_rewriting()`).
        **Medido, con costo real confirmado como sistematico**: los 3
        casos "no encontrado" que quedan en el dataset (`codigo_penal` ya
        no aplica, se convirtio en test positivo al cargar esa ley) dan el
        MISMO resultado final con y sin HyDE, solo que mas lento:
        consumidor 63.5s->145.6s (+82.1s), ley_federal_trabajo
        2.1s->78.3s (+76.2s, 37x), proteccion_animal 398.5s->448.0s
        (+49.5s, y ya no depende de HyDE -- el Codigo Penal Art.495 lo
        resuelve solo, confirmado en AMBOS modos). Patron confirmado:
        sistemico, no aislado.
        **Pre-check evaluado y DESCARTADO con evidencia real, no
        implementado**: se midio la similitud real (`dense_search`,
        threshold=0) de 8 preguntas genuinamente fuera del corpus (las 3
        del dataset + 5 sinteticas mas: propiedad industrial, visa de
        trabajo, ley de amparo, ISR federal, proteccion de datos/condominio
        de Chiapas reales pero no cargadas). Los 4 casos que quedan
        genuinamente por debajo del threshold real (nada pasa 0.5) se
        agrupan en **0.4471-0.4771** -- la MISMA banda donde vivia el caso
        que si se rescato este mismo dia (Art.1573/sucesion, 0.4765 antes
        de su fix). No hay separacion numerica limpia entre "genuinamente
        perdido" y "genuinamente cercano y rescatable" usando solo
        similitud cruda: un corte lo bastante alto para ahorrar en los 4
        casos medidos (necesitaria pasar de 0.4771) habria tenido buena
        chance de tambien bloquear HyDE en un futuro caso real tipo
        Art.1576 antes de que pudiera intentar ayudar; un corte mas seguro
        (0.40) no habria ahorrado nada en ninguno de los 4 casos medidos.
        **Decision: NO se implementa el pre-check de similitud cruda.**
        HyDE ya es fail-safe (nunca empeora un resultado final, solo
        agrega costo en un subconjunto de casos). Una señal mas rica (ej.
        si los candidatos sub-threshold vienen de una sola ley coherente
        vs. varias leyes dispersas, que podria discriminar mejor los dos
        grupos) queda anotada como idea futura, no justificada todavia sin
        mas evidencia -- mismo criterio de no sobre-ingenieria que el resto
        de la sesion
        `[Yo directamente, con las 8 mediciones reales de similitud antes
        de decidir]`
- [x] **Contextual retrieval** — **version barata evaluada con un
      experimento real, resultado negativo, NO se implementa la version
      cara de Anthropic.** `app/rag/chunker.py`
      `LegalChunk.to_embedding_text()` YA antepone contexto estructural
      determinista (ley/titulo-ordinal/capitulo/articulo) sin LLM. Se
      probo la version "barata" del problema real detectado en Fase 3.7
      (Art.1576, ver ahi el detalle completo del experimento): agregar el
      texto DESCRIPTIVO del Titulo (ej. "Titulo CUARTO (De la Sucesion
      Legitima)", no solo el ordinal) al contexto que se embebe. Medido en
      memoria contra el caso real que motivo la pregunta: la mejora fue
      **dentro del ruido (+0.0017) o incluso negativa (-0.0038) segun la
      variante de consulta** -- no justifica extender el chunker ni pagar
      el re-embed completo del corpus. La version CARA (LLM genera un
      resumen/contexto por chunk al indexar, la tecnica real de Anthropic)
      tampoco se implementa: si la version barata (mismo tipo de contexto,
      sin costo de LLM) no mostro beneficio medible en el caso que se sabe
      mas dificil del corpus, no hay evidencia de que la version cara
      (mas costosa, mas lenta de ingestar, mismo tipo de señal) vaya a dar
      un resultado distinto -- se evita sobre-ingenieria sin justificacion
      medida, mismo criterio que el documento fuente pide explicitamente
      `[Yo directamente, con el experimento documentado en Fase 3.7]`
- [x] **Reranking real** — **checklist desactualizado, ya completo desde
      Fase 3.7** (implementado ahi por necesidad real: el reranker
      placeholder era el sospechoso obvio antes de la investigacion de
      causas raiz del golden dataset). `app/rag/reranker.py` +
      `app/rag/reranker_router.py`: NVIDIA NIM
      (`nvidia/llama-nemotron-rerank-vl-1b-v2`) -> Jina
      (`jina-reranker-v2-base-multilingual`) -> heuristica local como
      ultimo recurso. Ver Fase 3.7 para el detalle completo (modelos
      verificados en vivo, invariante anti-alucinacion preservado
      independientemente de que proveedor responda)
- [x] Medir mejora antes/despues con el set de preguntas de regresion --
      **checklist desactualizado, ya completo desde Fase 3.7**:
      `tests/test_rag_regression.py` (24 preguntas reales, sin mocks) SI
      se uso para medir el reranker real antes/despues (17/2/5 con
      heuristica placeholder -> identico 17/2/5 con reranker real --
      conclusion honesta documentada en Fase 3.7: "medido, sin regresion,
      sin mejora medible en ESTE dataset", porque las causas raiz de los
      fallos estaban aguas arriba del reranking). El dataset crecio y se
      afino en corridas posteriores (llego a 22/2/0 tras el clasificador
      de grounding con chunks+few-shot) -- sigue siendo el instrumento de
      medicion para HyDE/contextual retrieval abajo

**Entregable: COMPLETO.** Los 4 items (1.1 query rewriting, 1.2 HyDE, 1.3
contextual retrieval, 1.4 reranking real) implementados/evaluados y medidos
contra el golden dataset real -- 22 passed/2 xfailed/0 failed, mejor
resultado de la sesion, con el cierre real del caso Art.1576 via HyDE.
Contextual retrieval se evaluo con un experimento real (resultado negativo,
no se implementa la version cara de Anthropic sin justificacion medida).
Fase 6 (RAG Avanzado / Nivel 2) cerrada.

---

## Fase 7 — Agentic RAG (Nivel 3)

Salto conceptual: el RAG deja de ser un pipeline lineal fijo. Se envuelve
todo lo de Fase 6 en un AGENTE que decide como proceder — las tecnicas de
Fase 6 se convierten en HERRAMIENTAS que el agente usa cuando lo considera
necesario, no pasos que siempre corren igual.

**Requiere Fase 6 completa y funcionando** (el documento fuente es explicito:
cada fase se construye sobre la anterior, no la reemplaza).

**Checklist (basado en las secciones 2.1-2.4 del documento fuente):**

- [x] **Etapa 1 completa** (ver detalle abajo): agente basico con LangGraph
      SIN loop de auto-evaluacion (eso lo agrega Etapa 2, ver abajo). El
      agente razona antes de actuar (decide que herramienta usar) y el set
      de herramientas ya esta construido sobre funciones existentes, no
      reescritas
      `[Subagente: logic]`, verificado independientemente por mi
- [x] **Etapa 2 completa**: auto-evaluacion (self-reflection) con reintento
      acotado, ver detalle completo abajo (diseno, evidencia real medida, y
      la decision de dejar `agentic_rag.self_reflection.enabled=false` por
      default) `[Subagente: logic]`, verificado independientemente por mi
- [x] Definir el set de herramientas del agente -- **implementadas 3 de las
      6 originales del documento fuente** (`search_laws`,
      `search_by_law`, `get_article`), construidas sobre funciones YA
      EXISTENTES de `app/rag/` (no reescritas). `rewrite_and_search` y
      `hyde_search` (las otras 2 del documento fuente) NO se
      implementaron como herramientas separadas -- decision de diseño: la
      Etapa 1 no incluye query rewriting/HyDE en absoluto (ver nota de
      alcance en `agent_pipeline.py`); Etapa 2 tampoco las expuso como
      herramientas separadas (fuera de alcance del reintento acotado, ver
      detalle abajo). `check_answer_quality` se resolvio en Etapa 2
      REUSANDO `app.rag.grounding.answer_is_grounded_in_practice` (ya
      existia) en vez de construir una funcion nueva, ver detalle abajo
      `[Subagente: logic]`
- [x] Implementar el flujo con LangGraph -- **version real confirmada:
      1.2.8** (dependencia transitiva de `langchain` 1.3.11, nunca fijada
      explicitamente antes; agregada a `requirements.txt` como
      `langgraph>=1.2,<2.0`). Grafo de 3 nodos sin loop:
      `START -> decidir -> buscar -> generar -> END`
      `[Subagente: logic]`
- [x] Verificar que el agente sigue respetando los guardrails de Fase 2.5 y
      el gate anti-alucinacion -- **verificado en el diseño Y con
      preguntas reales** (ver medicion abajo), no solo revisado en teoria
      `[Subagente: security]` + `[Subagente: bugs]` (verificacion real de
      invariantes la hice yo directamente via lectura de codigo + pruebas)

**Diseño real de Etapa 1** (`app/rag/agent_tools.py`, `app/rag/
agent_pipeline.py`, nuevos): ruta ALTERNATIVA, no reemplaza
`rag_pipeline.answer_question` -- bandera `ai_config.json`
`agentic_rag.enabled` (default `false`), `app/bots/conversation_store.py`
elige la ruta segun esa bandera. Grafo: nodo "decidir" (LLM barato,
`generate_with_fallback` temp=0.0, formato estructurado ACCION/LEY/
ARTICULO, con downgrade seguro a `busqueda_general` si el parseo falla o
faltan datos -- nunca un default mas arriesgado); nodo "buscar" (despacha a
`search_laws`/`search_by_law`/`get_article` segun la decision); nodo
"generar" (llama `generate_answer` sin modificarla).

**Invariantes anti-alucinacion preservadas, verificado explicitamente**:
Capa 1 de guardrails corre SIEMPRE antes del grafo, fuera del control del
agente. Para busqueda semantica (`busqueda_general`/`busqueda_por_ley`) el
gate es EXACTAMENTE `any(c.passed_threshold for c in chunks)`, el mismo
campo que solo `dense_search` puede poner. Para `articulo_especifico`
(`get_article`, lookup directo sin embeddings): decision de diseño
documentada extensamente en el codigo -- NO se reusa `passed_threshold=True`
para un chunk que no paso por similitud semantica real (ese campo tiene un
significado especifico del que depende `reranker.rerank` en otras rutas);
en su lugar usa su propio gate explicito (`len(chunks) > 0` -- el chunk es
una fila real de la DB, nunca inventada, asi que encontrarlo basta; no
encontrarlo es un "no encontrado" honesto). El segundo gate de grounding
(`answer_is_grounded_in_practice`, Fase 3.7) se aplica SIEMPRE despues de
generar, sin importar la ruta, solo puede degradar `True` a `False`.

**Bug real encontrado y arreglado por el subagente** (verificado
independientemente por mi): el parametro nuevo `document_filter` agregado a
`dense_search`/`sparse_search`/`hybrid_search` (`app/rag/retriever.py`,
para que `search_by_law` pueda acotar la busqueda a una sola ley) usaba
`:document_pattern::text IS NULL` en el SQL crudo -- SQLAlchemy interpreta
`::` como el cast shorthand de Postgres y NO sustituye el bind parameter
inmediatamente seguido de eso, dejando el literal `:document_pattern` sin
resolver en el SQL compilado -> `psycopg.errors.SyntaxError` en TODA
llamada a estas funciones (confirmado: rompia 4/4 tests en la primera
corrida de regresion antes del fix). Arreglado con
`CAST(:document_pattern AS text) IS NULL` -- reverificado con llamadas
reales con y sin filtro (`document_filter='Codigo Penal'` excluyo
correctamente todos los chunks de Ley de Amnistia).

**Bug real encontrado y arreglado por mi directamente** (no por el
subagente, quedo documentado como limitacion conocida en su reporte): el
parser de la decision del LLM (`_parse_decision` en `agent_pipeline.py`)
extraia SOLO el prefijo numerico del articulo pedido, descartando
cualquier sufijo latino ("15 Bis" -> "15"). Estos sufijos son comunes en
este corpus (Codigo Penal en particular tiene varios: "15 Bis", "326 Bis",
"228 Bis", ver `app/rag/chunker.py` para el mismo patron ya documentado en
el chunking) -- con el bug, CUALQUIER pregunta por un articulo con sufijo
via la ruta `articulo_especifico` fallaba a "no encontrado" aunque el
articulo existiera de verdad. Arreglado preservando el numero completo
(digitos + sufijo) en el parseo, y cambiando `get_article` a comparar
`UPPER(articulo_numero) = UPPER(:articulo)` (case-insensitive, tolera "15
Bis" vs "15 BIS"). Verificado con una llamada real: `get_article(db,
"codigo penal", "15 Bis")` y `get_article(db, "codigo penal", "15 BIS")`
ambas encuentran el chunk real correctamente ahora
`[Yo directamente, con verificacion en vivo antes/despues del fix]`.

**Limitacion conocida, NO arreglada, documentada** (baja urgencia, no
observada como problema real con los datos actuales): `get_article`'s
`ILIKE '%law_name%'` puede matchear MULTIPLES documentos a la vez (ej.
"codigo civil" matchea los 4 libros de Codigo Civil); sin `ORDER BY` +
`LIMIT 1`, una colision de `articulo_numero` entre esos libros podria
devolver un resultado arbitrario. No se ha observado con el corpus actual
(la numeracion de los 4 libros del Codigo Civil no se solapa en la
practica), pero es un gap real de diseño para leyes con nombres similares
en el futuro.

**MEDICION completa, reconstruida de 4 corridas parciales por
inestabilidad real del entorno de esta sesion** (background bash killeado
repetidas veces sin causa clara al principio; se encontro y corrigio una
causa real propia -- un comando mio con sintaxis de Windows `find /c`
corrido sin querer como el `find` de Unix en Git Bash, que recorrio TODO
el disco C: y probablemente compitio por recursos con las corridas de
pytest concurrentes; despues de matar ese proceso y limpiar, las corridas
subsiguientes completaron sin problema):
- **Pipeline lineal** (`agentic_rag.enabled=false`, default, sin cambios de
  codigo en esta ruta): `pytest tests/test_rag_regression.py -v -s`,
  reconstruido de 4 corridas parciales que juntas cubren las 24 preguntas
  sin overlap ni gaps (verificado explicitamente por nombre de test) --
  **20 passed, 2 xfailed, 2 failed**. Los 2 failed
  (`test_familiar_adulto_mayor_definicion`, `test_salud_certificados`) se
  verificaron INDEPENDIENTEMENTE, no se asumieron como regresion: en ambos
  casos, `hybrid_search` real (llamado directo, no via el test) confirma
  que el articulo esperado SI esta en el pool de candidatos con
  `passed_threshold=True` (paso el gate anti-alucinacion real), pero el
  reranker externo (llamada viva a NVIDIA/Jina, variable de por si) no lo
  selecciono al top-5 en esa llamada especifica -- mismo patron de
  variabilidad ya medido y aceptado en Fase 3.7 (el reranker no mejora
  sistematicamente estos casos limite), NO una regresion causada por
  `document_filter`. El delta contra el mejor baseline previo (22/2/0, con
  HyDE) es ruido de llamadas reales a un reranker externo, no un cambio de
  comportamiento
- **Subconjunto del agente** (`answer_question_agentic` directo, script de
  prueba, 7 preguntas representando las 4 rutas + guardrails): **7/7
  coherentes**, sin alucinaciones. `search_laws` (tortura, adopcion),
  `search_by_law` (codigo penal robo -- confirmado que TODOS los chunks
  devueltos eran exclusivamente de esa ley), `get_article` (articulo
  existente -- encontrado correctamente; articulo inexistente [99999] --
  admitido honestamente como no encontrado en 4.6s sin alucinar), Capa 1
  de guardrails (fuera de dominio, rechazado en 1.8s ANTES de invocar el
  grafo)

**Entregable Etapa 1: COMPLETO y medido**, comportamiento equivalente al
pipeline lineal en el subconjunto probado, invariantes preservadas.

---

### Etapa 2 — Self-reflection (reintento acotado)

**Diseno real** (`app/rag/agent_pipeline.py`, `_node_reformular`,
`_should_retry_after_generar`, `_build_graph`): se reuso el segundo gate ya
existente (`app.rag.grounding.answer_is_grounded_in_practice`, Fase 3.7) en
vez de construir `check_answer_quality` desde cero -- ya compara la
respuesta generada contra los chunks reales con un criterio calibrado (MISMO
tema vs. tema DISTINTO, 5 ejemplos few-shot). El grafo pasa de lineal a
condicional:

```
START -> decidir -> buscar -> generar -> (condicional) -> reformular -> buscar -> generar -> END
```

Nueva bandera `ai_config.json` `agentic_rag.self_reflection` (`enabled`,
`max_intentos=2`), mismo patron que `hyde`/`reranking`/`semantic_cache`. Con
la bandera apagada el grafo NI SIQUIERA registra el nodo/rama de reintento
(cero cambio de comportamiento vs. Etapa 1, verificado: `_build_graph(False)`
compila un grafo lineal identico al de Etapa 1).

**Que cambia entre intentos (decision de diseno, opcion (b) del enunciado
de la tarea, NO la (a))**: un LLM barato reformula el TEXTO de busqueda
(`_node_reformular`, mismo patron de fallback silencioso que
`app.rag.query_rewriting`/`app.rag.hyde`), pero el reintento SIEMPRE se
queda en la MISMA ruta que decidio el nodo "decidir" en el intento 1
(`busqueda_general` sigue siendo `busqueda_general`, `busqueda_por_ley` con
el mismo `law_name` sigue siendo `busqueda_por_ley`). Se descarto
explicitamente la opcion (a) (cambiar de ruta en el reintento, ej.
`busqueda_por_ley` -> `busqueda_general` cuando la ley no dio nada) con
evidencia real medida esta sesion (ver "cuando se activa" abajo): cambiar de
ruta reintroduciria el mismo falso positivo que la ruta original evitaba.
`articulo_especifico` y `ninguna` NUNCA reintentan (no hay ambiguedad de
fraseo que resolver en un lookup exacto por clave).

**Cuando se activa el reintento (los 4 deben cumplirse, ver
`_should_retry_after_generar`)**: ruta semantica (`busqueda_general`/
`busqueda_por_ley`) + `grounded_gate` primario fue `True` (SI hubo chunks
reales que pasaron el threshold, SI se genero con contenido real) +
`grounded` final es `False` (el segundo gate degrado) + `intentos <
max_intentos`. **Nunca reintenta cuando el gate primario ya fue False desde
el intento 1** -- decision tomada con evidencia real, no solo intuicion: se
midio en vivo que las 3 preguntas "no encontrado con falso positivo"
documentadas arriba (consumidor, ley federal del trabajo, proteccion
animal) YA terminan `grounded_gate=False` desde el intento 1 **dentro del
agente** (no del pipeline lineal, que si tenia el problema) -- el nodo
"decidir" identifica el nombre de ley mencionado explicitamente y toma
`busqueda_por_ley`, cuyo `document_filter` no matchea ningun documento real
para esas 3 leyes inexistentes, asi que `hybrid_search` devuelve `chunks=[]`
de entrada, sin llamar siquiera al LLM principal (4.4s-19.5s, `grounded=False`,
`model=None`, confirmado con `answer_question_agentic` real, sin mocks). Se
probo ademas, de forma independiente (`search_laws()` directo, forzando
`busqueda_general` sobre las mismas 3 preguntas), que **2 de las 3**
(consumidor, proteccion animal) SI cruzan `similarity_threshold=0.5` con
chunks de OTRAS leyes (Ley de Salud, Codigo Civil, Codigo Fiscal para
consumidor; Codigo Penal Art.494/495 y Ley de Salud Art.228 para animal) --
el mismo patron de falso positivo del bucket B ya documentado (Fase 3.7)
para el pipeline lineal. Esto confirma que reintentar CAMBIANDO de ruta
hacia `busqueda_general` cuando el gate primario ya fue False
REINTRODUCIRIA ese riesgo -- de ahi la decision de nunca cambiar de ruta y
nunca reintentar en ese escenario.

**MEDIDO contra el pipeline real** (`answer_question_agentic`, sin mocks,
NVIDIA NIM real): 5 preguntas x 2 corridas (`self_reflection.enabled=true` y
`=false`) -- las 3 preguntas "no encontrado" documentadas arriba (que ya
resuelve gratis la ruta `busqueda_por_ley`, ver arriba) mas 2 reformuladas a
proposito SIN nombrar una ley explicita para forzar la ruta
`busqueda_general` y poder ejercitar el bucket B real dentro del agente
(consumidor: "Puedo exigir la devolucion de mi dinero si compre un producto
defectuoso en una tienda de Chiapas?"; animal: "Es delito no cuidar bien a
mi perro o gato en Chiapas?"; mas una reformulacion de la de trabajo: "Que
pasa si me despiden injustamente de mi trabajo en una empresa privada de
Chiapas?"), mas 2 preguntas que ya funcionan bien (tortura, Codigo Penal
robo) para confirmar que el loop NO se activa quando no hace falta:
- **El reintento se disparo 1 de 5 veces** (pregunta de trabajo
  reformulada, corrida CON self_reflection): intento 1 -> `busqueda_general`
  -> chunks de Ley del Servicio Civil pasaron threshold pero el segundo gate
  dio `NO` -> `_node_reformular` genero una reformulacion real y distinta
  ("Cual es el procedimiento legal para reclamar despido sin justificacion
  ante el Tribunal de Conciliacion y Arbitraje en Chiapas?") -> intento 2
  -> el segundo gate volvio a dar `NO` -> tope duro (`intentos=2 ==
  max_intentos=2`) respetado sin excepcion, `grounded=False` final, sin
  alucinar (la respuesta final admitio explicitamente que no podia
  responder con los fragmentos disponibles).
- **No cambio el resultado final en ese caso** (se quedo correctamente en
  `grounded=False` con y sin el reintento) -- limitacion real de la muestra
  de esta sesion: no se obtuvo un caso real donde el reintento convirtiera
  `False` en `True` con una respuesta genuinamente mejor. La no-determinismo
  ya documentada extensamente en Fase 3.7 (temperature=0.1 en la generacion
  principal produce texto distinto en cada corrida, y el segundo gate
  reacciona distinto a eso) domino la comparacion: la MISMA pregunta de
  trabajo, en la corrida SIN self_reflection, dio `grounded=True` en el
  intento unico (sin necesitar reintento) -- confirma que el resultado de
  estas preguntas limite varia entre corridas independientemente de esta
  bandera, no solo por ella.
- **Costo extra real**: la pregunta que SI reintento tardo 251.9s (2
  intentos completos: busqueda+generacion+clasificador x2, mas la
  reformulacion) vs. 84.5-119.8s de un intento unico comparable en la
  corrida sin self_reflection -- aproximadamente 2x, tal como se anticipo en
  el enunciado de la tarea. Para las 4/5 preguntas donde el intento 1 ya
  tuvo exito, el costo extra fue CERO (confirmado por logs: ni una llamada
  de reformulacion en esos casos, en ninguna de las dos corridas).
- **Tope duro respetado sin excepcion**: en las 10 ejecuciones reales (5
  preguntas x 2 corridas) nunca se supero `intentos=2`, confirmado por logs
  (una sola linea de "agente reformular" en total, para la pregunta de
  trabajo en la corrida con la bandera activa).

**Decision final: `agentic_rag.self_reflection.enabled=false`** (mismo
default que `agentic_rag.enabled`). Mismo criterio ya aplicado a HyDE/
reranker en este proyecto: no se asume beneficio, se mide. Con la evidencia
real de esta sesion -- el mecanismo funciona correctamente end-to-end
(reformula con terminologia genuina, respeta el tope duro, nunca alucina),
pero (1) las 3 preguntas objetivo originales ya se resuelven gratis por la
ruta `busqueda_por_ley` sin necesitar el reintento, (2) en la unica corrida
real donde SI se activo, no cambio el resultado final, y (3) el costo
cuando se activa es ~2x -- no hay evidencia medida todavia de una mejora de
precision que justifique el costo por default. Queda disponible via config
para medirse mas a fondo (mas preguntas, mas corridas) sin tocar codigo
`[Subagente: logic]`, verificado independientemente por mi (corridas
propias `answer_question_agentic` con y sin la bandera, logs reales
revisados linea por linea, no solo el resumen del subagente).

**Entregable:** un agente que razona sobre como buscar, se auto-evalua, y
busca iterativamente — verificado contra el mismo set de preguntas de
regresion, mas casos donde la iteracion/auto-evaluacion deberia activarse.

---

## Fase 8 — GraphRAG (Nivel 4)

El nivel frontera, opcional/avanzado segun el documento fuente. En vez de
tratar las leyes como chunks sueltos, se construye un GRAFO de conocimiento
con las relaciones entre ellas (reforma, deroga, remite_a, deriva_de,
modifica). Se agrega como una herramienta MAS del agente de Fase 7, no
reemplaza nada de lo anterior.

**Requiere Fase 7 completa** (el grafo se integra como herramienta del
agente, necesita el agente ya funcionando).

**Verificacion previa (2026-07-23):** antes de comprometerse a construir
esto, se confirmo que el corpus YA ingerido tiene senal real para un grafo,
no es un ejercicio artificial. Query directa sobre `chunks.content` con
`ILIKE '%abroga%' OR '%deroga%' OR '%se reforma%' OR '%remite%'` devolvio
**473 chunks** con marcadores estructurados tipo
`(DEROGADO POR ARTICULO TERCERO TRANSITORIO DE LA LEY DE ASISTENCIA E
INTEGRACION DE LAS PERSONAS ADULTAS MAYORES DEL ESTADO DE CHIAPAS, P.O. 31
DE DICIEMBRE DE 2015)` y `(REFORMADO, P.O. 23 DE SEPTIEMBRE DE 2009)` —
formato consistente en todo el corpus (viene del Periodico Oficial). Esto
confirma que hay relaciones reales entre leyes ya en la base, no solo
hipoteticas.

**Decision de arquitectura: grafo modelado en PostgreSQL, NO Neo4j, NO
NetworkX.** Razones:
- Ya hay una instancia Postgres+pgvector corriendo para este proyecto
  (puerto 5433) — cero infraestructura nueva, mismo patron psycopg v3 que
  el resto del codigo.
- El volumen es chico (18 documentos activos, del orden de decenas/pocas
  centenas de aristas esperadas) — no justifica operar un motor de grafos
  aparte para un proyecto de portafolio.
- NetworkX se descarta porque no persiste entre reinicios del proceso sin
  un paso de serializacion aparte, y la herramienta del agente necesita
  poder consultarlo en cualquier request sin recalcular desde texto crudo.
- Neo4j se descarta por el mismo criterio ya aplicado a WhatsApp/Baileys en
  Fase 5: infraestructura nueva que hay que mantener, sin beneficio medido
  que lo justifique sobre modelar dos tablas en la base que ya existe.

**Decision de extraccion: regex/parsing deterministico primero, LLM solo
si hace falta.** Los marcadores `(DEROGADO...)` / `(REFORMADO...)` del
Periodico Oficial siguen un formato lo bastante regular para extraerse sin
LLM (mismo criterio que `legal_synonyms.py` y el rechazo de Contextual
Retrieval cara en Fase 6: preferir deterministico cuando cubre el caso
real, reservar LLM para lo que de verdad lo necesita — aqui, relaciones en
prosa libre dentro de articulos Transitorios que no siguen el patron fijo).

**Checklist (basado en las secciones 3.1-3.4 del documento fuente):**

- [x] Elegir donde vive el grafo — **decidido: PostgreSQL**, ver
      justificacion arriba `[Subagente: database]`
- [x] Disenar y crear las tablas del grafo (`legal_relations`/aristas: from,
      to, tipo de relacion reforma/deroga/adiciona, articulo origen, fecha,
      texto fuente) — modelo `app/models/legal_relation.py`, tabla real
      creada y poblada `[Subagente: database]`
- [x] Extraer relaciones de los chunks candidatos con regex sobre los
      marcadores estructurados (`ingestion/extract_legal_relations.py`) --
      **2004 filas reales** en `legal_relations` (1764 auto-modificacion, 81
      cross-ley resueltas a otro documento del corpus, 159 cross-ley con
      `to_document_id` NULL porque esa ley no esta ingerida todavia). No
      hizo falta pasada LLM aparte -- el regex sobre los dos formatos de
      marcador del Periodico Oficial (participio y "PUBLICADA") cubrio el
      caso real `[Subagente: data-extraction]`
- [x] Agregar la herramienta `query_graph(law)` al agente de Fase 7
      `[Subagente: logic]` -- **completo, ver evidencia abajo.**
- [x] Probar con preguntas que solo el grafo puede responder bien contra
      RAG normal, para demostrar la diferencia `[Subagente: logic]` --
      **completo, ver evidencia abajo.**

**Entregable:** sistema que navega relaciones legales ademas de recuperar
texto — nivel senior/frontera segun el documento fuente. Opcional: el
documento fuente marca esta fase como la de mayor costo/complejidad relativa
al beneficio, no bloquea el resto del proyecto si se decide no hacerla.

### Fase 8 -- integracion en el agente (completada, sesion 2026-07-23)

**Codigo:**
- `app/rag/agent_tools.py`: `query_graph(db, law_name, articulo=None,
  limit=20) -> list[dict]` (consulta `legal_relations` por `from_document_id`
  O `to_document_id` matcheando `law_name`, ordenado por fecha DESC,
  truncado a `limit` con `logger.info` explicito de cuantas filas se
  omitieron -- nunca se mete ese conteo en el contenido de un chunk).
  `relations_to_chunks(relations) -> list[RetrievedChunk]` (formatea cada
  fila real como una oracion en espanol via `_relation_to_sentence`, mismo
  patron que `get_article`: `similarity=1.0`, `passed_threshold=False` a
  proposito, `chunk_id` = `from_chunk_id` REAL de la tabla `chunks`, no un
  id inventado).
- `app/rag/agent_pipeline.py`: 5ta accion `HISTORIAL_LEY` en
  `DECIDE_SYSTEM_PROMPT`/`_VALID_DECISIONS`/`_parse_decision` (downgrade a
  `busqueda_general` si no hay `ley`, mismo criterio que
  `busqueda_por_ley`/`articulo_especifico`). Nueva rama en `_node_buscar`
  que llama `query_graph(db, state["law_name"], articulo=state.get("articulo"))`.
  Gate propio en `_node_generar` (`grounded_gate = len(chunks) > 0`,
  compartido con `articulo_especifico` -- ver invariante 6 nueva en el
  docstring de modulo). `_should_retry_after_generar` NUNCA reintenta esta
  ruta sin tocar la funcion (su lista blanca solo nombra
  busqueda_general/busqueda_por_ley, `historial_ley` cae fuera solo).

**2 bugs reales encontrados y corregidos contra la DB real durante la
verificacion (no en teoria, con preguntas reales):**

1. **Bug de retrieval por orden/limite:** `query_graph` sin filtro de
   articulo trae "las N relaciones mas recientes de TODA la ley" -- para una
   pregunta sobre un articulo puntual ("que le paso al articulo 93 del
   Codigo de Atencion a la Familia") eso podia dejar la relacion real del
   articulo pedido FUERA del top-20 si la ley tenia muchas relaciones mas
   recientes en OTROS articulos (medido: 159 de las 294 relaciones de esa
   ley son mas recientes que la del articulo 93). El segundo gate de
   grounding atrapo correctamente el caso (no alucino), pero la respuesta
   correcta existia y no se encontraba -- fallo de RETRIEVAL. Fix: `_node_buscar`
   ahora pasa `state["articulo"]` (ya lo extraia `_parse_decision`, solo no
   se usaba) a `query_graph`, que con `articulo` presente filtra EXACTO por
   `from_articulo` en vez de traer solo por fecha.
2. **Bug de matching por puntuacion:** el LLM de "decidir" devuelve el
   nombre de la ley SIN la puntuacion del nombre oficial (ej. "ley de los
   derechos de ninas ninos y adolescentes" sin la coma que
   `documents.nombre` SI tiene: "Ninas, Ninos"). Un `ILIKE '%...%'` literal
   nunca matcheaba, y `query_graph` devolvia `[]` para una ley que si existe
   y si tiene historial real -- indistinguible de "esta ley no existe".
   Confirmado con query directa a la DB real (0 filas) antes de escribir el
   fix. Fix (`_fuzzy_ilike_pattern`, SOLO dentro de `query_graph`, no se
   toco `get_article` ni `search_by_law`/`hybrid_search` que tienen su
   propio ILIKE ya existente): cada corrida de whitespace del nombre
   buscado se reemplaza por un comodin `%`, tolerando cualquier caracter
   (coma, guion, espacio extra) entre palabras.

**Evidencia real (comandos + output crudo, contra Postgres/pgvector real y
NVIDIA NIM real, sin mocks):**

Suite offline completa (nuevo archivo `tests/test_agent_pipeline_historial_ley.py`,
18 tests nuevos verificados uno por uno -- conteo corregido de 21 a 18 tras
verificacion independiente, ver mas abajo: parsing de `HISTORIAL_LEY`/downgrade,
`_should_retry_after_generar` nunca reintenta esta ruta, `_relation_to_sentence`/
`relations_to_chunks` para self-mod/cross-ley-resuelta/cross-ley-sin-resolver/
sin-fecha/sin-articulo, `_fuzzy_ilike_pattern`), comando y resultado real:

```
pytest tests/ -v --ignore=tests/test_rag_regression.py
...
======================== 46 passed, 1 warning in 3.61s ========================
```

(28 tests previos de Etapa 1/2 + chunker + guardrails, todos siguen en
verde -- no se toco su logica. Verificado independientemente por mi:
`pytest tests/test_agent_pipeline_historial_ley.py -v` -> 18 passed,
`pytest tests/ --ignore=tests/test_rag_regression.py -q` -> 46 passed,
ambos corridos yo mismo, mismo resultado que reporto el subagente.)

`tests/test_rag_regression.py` (35min, costo real de API) NO se corrio esta
sesion -- no se toco `rag_pipeline.py`/`generator.py`/`grounding.py`, fuera
del alcance de este cambio; se deja pendiente si se quiere una confirmacion
adicional.

Comparacion real `answer_question_agentic` (ruta `historial_ley`) vs
`rag_pipeline.answer_question` (pipeline lineal), preguntas reales
verificadas contra `legal_relations` antes de preguntar:

1. **"Que le paso al articulo 93 del Codigo de Atencion a la Familia?"**
   (verificado en DB: derogado 2015-06-17 por Ley de los Derechos de Ninas,
   Ninos y Adolescentes, `to_document_id=11`, resuelto)
   - Agentico (`historial_ley`): `grounded=True`. Respuesta: *"El articulo
     93 ... fue derogado ... el 17 de junio de 2015, cuando entro en vigor
     la Ley de los Derechos de Ninas, Ninos y Adolescentes del Estado de
     Chiapas, segun se establece en el articulo tercero transitorio de esa
     nueva ley..."* -- correcto, articulo/fecha/ley exactos.
   - Lineal (RAG semantico normal): `grounded=False`. Respuesta: *"no cuento
     con informacion sobre el articulo 93... Los unicos articulos de ese
     codigo que aparecen en los fragmentos son el 146..."* -- el retrieval
     semantico normal no trae el articulo 93 en absoluto (dense_search sobre
     el TEXTO del articulo no compite bien contra la pregunta sobre su
     HISTORIA), se niega honestamente pero no puede responder. Diferencia
     real y medida.

2. **"Que le paso al articulo 171 del Codigo de Atencion a la Familia de
   Chiapas?"** (verificado en DB: 2 derogaciones reales -- 2014-11-27
   auto-modificacion, y 2015-09-21 por "Ley para la Inclusion de las
   Personas con Discapacidad", `to_document_id=NULL`, ley no ingerida)
   - Agentico: `grounded=True`, menciona AMBAS fechas/eventos por separado
     y admite honestamente *"la cual actualmente no se encuentra dentro del
     corpus legal disponible para consulta"* para la ley no ingerida --
     grounded en los 3 chunks sinteticos reales (`chunks: [('Codigo de
     Atencion a la Famili', '171')]` x3).
   - Lineal: tambien `grounded=True` (el articulo 171 SI aparece en top-K
     semantico esta vez) y con contenido correcto, pero porque el chunk de
     ese articulo especifico trae el marcador embebido en su texto -- una
     coincidencia de que ese articulo puntual si califico en similarity,
     no algo que el pipeline lineal pueda garantizar en general (ver caso 1
     y 3).

3. **"Cuando se reformo el articulo 15 de la Ley de los Derechos de Ninas,
   Ninos y Adolescentes de Chiapas?"** (verificado en DB: auto-modificacion
   2022-06-15, P.O. 229)
   - Agentico (post-fix de los 2 bugs de arriba): `grounded=True`. Respuesta:
     *"El articulo 15 ... fue reformado el 15 de junio de 2022. Esta reforma
     fue publicada en el Periodico Oficial del estado con el numero 229..."*
     -- exacto.
   - Lineal: `grounded=True` pero **no puede responder la pregunta real**:
     *"no es posible determinar la fecha exacta de la reforma... El
     fragmento del articulo 15 ... no presenta esa informacion"* -- trajo el
     TEXTO del articulo 15 (correcto semanticamente) pero ese chunk no
     contiene la fecha de reforma en su marcador visible al LLM de esa
     forma; `grounded=True` aqui es un falso-positivo de utilidad (esta
     fundamentado pero no responde lo pedido). El grafo si responde.

4. **"Que reformas ha tenido la Ley de los Derechos de Ninas, Ninos y
   Adolescentes del Estado de Chiapas?"** (historial completo, sin articulo
   puntual; verificado en DB: 8 relaciones self-mod reales: Art.15
   2022-06-15, Art.159/145/49/147 reforma + Art.51 adiciona 2017-04-26,
   Art.2/38 adiciona 2017-02-01)
   - Agentico: `grounded=True`, tarda 3s cuando `query_graph` no encuentra
     nada (antes del fix, `[]` por el bug de puntuacion) y ~387s cuando si
     responde correctamente citando LAS 8 fechas/articulos/numeros de P.O.
     reales, en 3 parrafos agrupados por fecha de publicacion -- ningun dato
     inventado, todo trazable a `legal_relations`.
   - Lineal (452s): responde con 3 reformas (Art.135, 159, 171) tomadas de
     texto semanticamente similar, pero **ninguna coincide exactamente con
     los articulos reales que si tuvieron reforma segun `legal_relations`**
     para esta ley (el 135 y 171 no estan en la lista de 8 self-mod reales
     verificada arriba) -- el pipeline lineal arma una respuesta con
     fragmentos de otros articulos que SI tienen marcadores de reforma en su
     texto pero no es la lista completa/correcta, mientras que el grafo
     consulta la fuente de verdad estructurada directamente.

**Por que no reintenta (Etapa 2):** confirmado con test offline
(`test_historial_ley_never_retries_even_with_gate_true_and_not_grounded`,
`test_historial_ley_never_retries_regardless_of_intentos`) -- no hizo falta
tocar `_should_retry_after_generar`, su condicion 1 ya excluye cualquier
decision fuera de `busqueda_general`/`busqueda_por_ley`.

---

## Iniciativa paralela — Frontend web (chat publico + dashboard)

Documento fuente completo: **`WEB_FRONTEND_PLAN.md`** (raiz del repo).
**Esa es la fuente de verdad para esta iniciativa — no duplicar su contenido
aqui, solo este puntero.** La lleva otra sesion/agente por separado; este
archivo (`PLAN.md`) no se actualiza con el detalle de sus fases (A-D) para no
chocar con ese trabajo en curso.

Resumen minimo para orientarse: agrega un canal web (Next.js en
`lexchiapas-web/`, separado del backend FastAPI) con chat publico — mismo
`rag_pipeline.answer_question()`, mismo grounding/citas/disclaimer que
Telegram, sin necesitar Telegram para probarlo — mas un dashboard privado de
metricas (uso, calidad del RAG, costo/performance) protegido por el
`ADMIN_API_KEY` que ya existe. Requiere Fase 1 de este documento ya resuelta
(lo esta). No esta bloqueado por Fase 2.5 (guardrails) ni por Fase 3
(Telegram) — es un track paralelo, no secuencial.

Si se retoma trabajo aqui en `PLAN.md` y hay dudas sobre si algo choca con el
frontend web (ej. cambios de schema en `messages`, nuevos endpoints en
`app/api/`), revisar `WEB_FRONTEND_PLAN.md` primero.

---

## Notas para quien retome esto

- El chunker ya tuvo un bug real encontrado por su propio test (headers de
  capitulo no reseteaban el articulo activo, duplicando chunks). Cualquier
  cambio a `app/rag/chunker.py` deberia correr `pytest tests/test_chunker.py`
  antes de darse por bueno.
- Los nombres de modelo en `ai_config.json` son ilustrativos — confirmar en
  build.nvidia.com antes de asumir que existen.
- Los scrapers ya se probaron contra las paginas reales (ver checklist de
  Fase 1 arriba). `congreso_scraper.py` sigue sin funcionar (la pagina carga
  el listado por JavaScript); `consejeria_scraper.py` si funciona de punta a
  punta despues del fix de `BASE_URL` y de leer el nombre desde la fila de
  la tabla en vez del link.
- Ya hay una ley real descargada, parseada y chunkeada correctamente:
  `lexchiapas/data/raw/ley_de_amnistia.pdf` /
  `lexchiapas/data/processed/ley_de_amnistia.txt`. Lista para cargarse de
  verdad con `embed_and_store_chunks` (la API key de NVIDIA ya esta puesta).

---

## Entorno real (actualizado 2026-07-07)

- Maquina tiene **dos instalaciones de PostgreSQL**: 14 (puerto 5432, la que
  el usuario usa normalmente para otras cosas, NO tocar) y **18 (puerto 5433,
  la que usa este proyecto)**.
- **pgvector 0.8.4 ya esta compilado e instalado** para PostgreSQL 18.
  Importante: **pgvector 0.8.0 no compila contra PG18** (cambio de firma en
  `vacuum_delay_point` en el vacuum de Postgres 18); hizo falta la 0.8.4. Si
  en el futuro hay que reinstalarlo o migrar de version de Postgres, clonar
  pgvector con el tag mas reciente, no uno viejo.
- Compilar pgvector en Windows requirio Visual Studio 2022 (Community, ya
  estaba instalado) + `vcvars64.bat` + `nmake /F Makefile.win` con
  `PGROOT=C:\Program Files\PostgreSQL\18`. El paso `nmake ... install` copia
  archivos dentro de `Program Files`, que requiere permisos de administrador
  (dio "Acceso denegado" corriendo como usuario normal) — se resolvio con un
  `.bat` elevado via `Start-Process -Verb RunAs` (dispara un prompt de UAC).
- Base de datos: `lexchiapas`, rol de aplicacion: `lexchiapas` /
  `lexchiapas_dev` (password de desarrollo, no es secreto de produccion).
  Extension `vector` habilitada dentro de esa base especificamente (no en
  `postgres` ni en las demas).
- `DATABASE_URL` real en `.env.example`:
  `postgresql+psycopg://lexchiapas:lexchiapas_dev@localhost:5433/lexchiapas`
- Verificado con una query `SELECT '[1,2,3]'::vector <=> '[1,2,3]'::vector;`
  conectado como el rol `lexchiapas` — el tipo `vector` funciona de punta a
  punta.
- **Las 6 tablas ya existen** en la base `lexchiapas` (`documents`, `chunks`,
  `conversations`, `messages`, `feedback`, `ingestion_logs`), creadas con
  `Base.metadata.create_all(engine)` importando `app.models`. Confirmado por
  `\dt` y `\d chunks`: `chunks.embedding` es `vector(1024)`.
- `requirements.txt` ya esta instalado en el entorno conda
  `lexchiapas-chatbot-legal-rag-brief` (el que usa `python`/`pytest` en esta
  maquina).
- Existe un **`.env` real** (no `.env.example`) en `lexchiapas/` con
  `DATABASE_URL` apuntando a la base real, `ADMIN_API_KEY=dev-admin-key`, y
  **`NVIDIA_API_KEY` ya cargado** (el usuario la consiguio en
  build.nvidia.com).
- **FASE 1 COMPLETA.** Pipeline RAG probado end-to-end contra datos y
  servicios reales: la **Ley de Amnistia del Estado de Chiapas** (ley real,
  7 articulos) esta cargada en la base `lexchiapas` con embeddings reales de
  `nvidia/nv-embedqa-e5-v5` (`document.id=4`). `answer_question()` probado
  con preguntas reales: cita el articulo correcto en casos relevantes y
  rechaza correctamente (`grounded: False`, sin llamar al LLM) una pregunta
  fuera de dominio. En el camino se encontraron y arreglaron 4 bugs reales
  (ver "Bugs reales encontrados" en el checklist de Fase 1 arriba):
  `input_type` faltante en embeddings, cast de `vector` faltante en SQL
  crudo, el gate de `grounded` que no distinguia dense (con threshold real)
  de sparse (sin threshold real), y el `similarity_threshold` de 0.75 que
  estaba mal calibrado (recalibrado a 0.5 con evidencia real).
- No queda ningun pendiente bloqueante de Fase 1. Lo que sigue es Fase 2
  (cargar mas leyes, afinar threshold con mas datos, reranker real, etc.).
- **Corpus actual (Fase 2 en progreso):** 4 documentos reales, 109 chunks
  totales, todos con embeddings reales. `documents.id` 4 (Amnistia, 7
  chunks), 7 (Bibliotecas, 43 chunks), 8 (Tortura, 14 chunks), 9 (Adopcion,
  45 chunks). Ver checklist de Fase 2 arriba para el detalle completo,
  incluyendo 4 bugs reales mas encontrados al pasar de 1 a 4 leyes (el mas
  importante: `app/rag/reranker.py` dejaba que scores inflados de BM25
  desplazaran del top-K a matches reales de dense_search, causando falsos
  negativos de `grounded` — invisible con una sola ley en el corpus).
