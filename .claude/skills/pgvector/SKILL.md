---
name: pgvector
description: Reference for pgvector setup and similarity queries in LexChiapas (PostgreSQL vector store, columna embedding en la tabla chunks). Use when writing or debugging app/database.py, app/models/*, or any dense-search SQL.
---

# pgvector — referencia rapida

LexChiapas guarda los embeddings como columna `vector` DENTRO de la tabla
`chunks` en PostgreSQL — no hay una base de datos vectorial separada.

## Instalacion (Windows)

`CREATE EXTENSION vector;` requiere que la extension este compilada/
instalada en el binario de PostgreSQL primero (en Windows es un paso manual
extra, no viene por defecto). Si una query con `vector` falla con "type
vector does not exist", el problema casi siempre es que la extension no esta
instalada, no un bug de codigo.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id),
    articulo_numero TEXT,
    titulo TEXT,
    capitulo TEXT,
    seccion TEXT,
    content TEXT NOT NULL,
    chunk_metadata JSONB,
    embedding vector(1024),  -- dimension debe coincidir con el modelo NV-Embed usado
    created_at TIMESTAMPTZ DEFAULT now()
);
```

## Busqueda por similitud (dense search)

```sql
SELECT id, content, articulo_numero, titulo,
       1 - (embedding <=> %(query_vector)s) AS similarity
FROM chunks
WHERE 1 - (embedding <=> %(query_vector)s) > 0.75   -- threshold anti-alucinacion
ORDER BY embedding <=> %(query_vector)s
LIMIT %(k)s;
```

- `<=>` es distancia coseno en pgvector (menor = mas similar).
- El threshold (`> 0.75` sugerido) va ANTES de generar la respuesta: si la
  query no devuelve filas, el sistema responde "no encontre informacion",
  no debe llamar al LLM con chunks debiles.
- Usar psycopg v3 con parametros nombrados/posicionales, nunca interpolar el
  vector o el texto de la query en el SQL como string.

## Indices (cuando crece el volumen)

Para mas que un puñado de leyes, agregar un indice para no hacer sequential
scan:

```sql
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
-- o ivfflat si hnsw no esta disponible en la version instalada
```

## Cosas que romper facil

- Cambiar el modelo de embeddings sin re-generar los vectores existentes
  deja embeddings de dimensiones distintas mezclados (o un error directo si
  la columna tiene dimension fija).
- Olvidar el `WHERE` del threshold y dejar que cualquier resultado, por bajo
  que sea el score, llegue al LLM — esto es la causa mas comun de
  alucinacion en este proyecto.
