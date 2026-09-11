--
-- PostgreSQL database dump
--

\restrict bcb8k9g0z45oufOCKgzHoxK5RHHrhglClHe61fkJ4JiGzoGbgAhHMSXaRBElowg

-- Dumped from database version 18.0
-- Dumped by pg_dump version 18.0

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: alembic_version; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.alembic_version (
    version_num character varying(32) NOT NULL
);


--
-- Name: chunks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.chunks (
    id integer NOT NULL,
    document_id integer NOT NULL,
    articulo_numero character varying(50),
    titulo character varying(200),
    capitulo character varying(200),
    seccion character varying(200),
    content text NOT NULL,
    chunk_metadata jsonb,
    embedding public.vector(1024),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    embedding_model character varying(200) DEFAULT 'nvidia/llama-nemotron-embed-vl-1b-v2'::character varying NOT NULL
);


--
-- Name: chunks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.chunks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: chunks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.chunks_id_seq OWNED BY public.chunks.id;


--
-- Name: conversations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.conversations (
    id integer NOT NULL,
    platform character varying(20) NOT NULL,
    user_id character varying(100) NOT NULL,
    chat_id character varying(100) NOT NULL,
    started_at timestamp with time zone DEFAULT now() NOT NULL,
    last_message_at timestamp with time zone,
    CONSTRAINT ck_conversations_platform CHECK (((platform)::text = ANY ((ARRAY['telegram'::character varying, 'whatsapp'::character varying, 'web'::character varying])::text[])))
);


--
-- Name: conversations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.conversations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: conversations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.conversations_id_seq OWNED BY public.conversations.id;


--
-- Name: documents; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.documents (
    id integer NOT NULL,
    nombre character varying(300) NOT NULL,
    tipo character varying(50) NOT NULL,
    fecha_publicacion date,
    fecha_ultima_reforma date,
    source_url character varying(500),
    area_derecho character varying(150),
    is_active boolean NOT NULL,
    ingested_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: documents_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: documents_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.documents_id_seq OWNED BY public.documents.id;


--
-- Name: feedback; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.feedback (
    id integer NOT NULL,
    message_id integer NOT NULL,
    rating character varying(20) NOT NULL,
    user_comment text,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_feedback_rating CHECK (((rating)::text = ANY ((ARRAY['util'::character varying, 'no_util'::character varying])::text[])))
);


--
-- Name: feedback_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.feedback_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: feedback_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.feedback_id_seq OWNED BY public.feedback.id;


--
-- Name: golden_dataset_run_cases; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.golden_dataset_run_cases (
    id integer NOT NULL,
    run_id integer NOT NULL,
    pregunta text NOT NULL,
    passed boolean,
    expects_grounded boolean,
    actual_grounded boolean,
    articulo_esperado character varying(50),
    posicion_encontrada integer,
    respuesta_snippet character varying(250)
);


--
-- Name: golden_dataset_run_cases_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.golden_dataset_run_cases_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: golden_dataset_run_cases_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.golden_dataset_run_cases_id_seq OWNED BY public.golden_dataset_run_cases.id;


--
-- Name: golden_dataset_runs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.golden_dataset_runs (
    id integer NOT NULL,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    total integer,
    passed integer,
    xfailed_known integer,
    failed integer,
    duration_ms integer
);


--
-- Name: golden_dataset_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.golden_dataset_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: golden_dataset_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.golden_dataset_runs_id_seq OWNED BY public.golden_dataset_runs.id;


--
-- Name: ingestion_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ingestion_logs (
    id integer NOT NULL,
    document_id integer,
    status character varying(30) NOT NULL,
    chunks_created integer,
    error_message text,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    CONSTRAINT ck_ingestion_logs_status CHECK (((status)::text = ANY ((ARRAY['running'::character varying, 'success'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: ingestion_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.ingestion_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: ingestion_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.ingestion_logs_id_seq OWNED BY public.ingestion_logs.id;


--
-- Name: legal_relations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.legal_relations (
    id integer NOT NULL,
    from_document_id integer,
    from_chunk_id integer,
    from_articulo character varying(50),
    relation_type character varying(30) NOT NULL,
    to_document_id integer,
    to_law_name_raw character varying(300) NOT NULL,
    fecha date,
    source_text text NOT NULL,
    extraction_method character varying(20) NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_legal_relations_extraction_method CHECK (((extraction_method)::text = ANY ((ARRAY['regex'::character varying, 'regex_publicada'::character varying, 'regex_se_verbo'::character varying])::text[]))),
    CONSTRAINT ck_legal_relations_relation_type CHECK (((relation_type)::text = ANY ((ARRAY['deroga'::character varying, 'reforma'::character varying, 'adiciona'::character varying])::text[])))
);


--
-- Name: legal_relations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.legal_relations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: legal_relations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.legal_relations_id_seq OWNED BY public.legal_relations.id;


--
-- Name: messages; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.messages (
    id integer NOT NULL,
    conversation_id integer NOT NULL,
    role character varying(20) NOT NULL,
    content text NOT NULL,
    retrieved_chunks jsonb,
    llm_model character varying(100),
    response_time_ms integer,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    prompt_tokens integer,
    completion_tokens integer,
    found_answer boolean,
    error_message text,
    grounding_classifier_model character varying(100),
    was_rewritten boolean,
    jailbreak_detected boolean DEFAULT false NOT NULL,
    search_time_ms integer,
    generation_time_ms integer,
    agent_trace jsonb,
    aux_prompt_tokens integer,
    aux_completion_tokens integer,
    CONSTRAINT ck_messages_role CHECK (((role)::text = ANY ((ARRAY['user'::character varying, 'assistant'::character varying])::text[])))
);


--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.messages_id_seq OWNED BY public.messages.id;


--
-- Name: semantic_cache; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.semantic_cache (
    id integer NOT NULL,
    question_text text NOT NULL,
    question_embedding public.vector(1024) NOT NULL,
    response_json jsonb NOT NULL,
    corpus_chunk_count integer NOT NULL,
    corpus_max_chunk_id integer NOT NULL,
    hit_count integer DEFAULT 0 NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    last_used_at timestamp with time zone DEFAULT now() NOT NULL,
    embedding_model character varying(200) DEFAULT 'nvidia/llama-nemotron-embed-vl-1b-v2'::character varying NOT NULL
);


--
-- Name: semantic_cache_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.semantic_cache_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: semantic_cache_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.semantic_cache_id_seq OWNED BY public.semantic_cache.id;


--
-- Name: chunks id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks ALTER COLUMN id SET DEFAULT nextval('public.chunks_id_seq'::regclass);


--
-- Name: conversations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations ALTER COLUMN id SET DEFAULT nextval('public.conversations_id_seq'::regclass);


--
-- Name: documents id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents ALTER COLUMN id SET DEFAULT nextval('public.documents_id_seq'::regclass);


--
-- Name: feedback id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.feedback ALTER COLUMN id SET DEFAULT nextval('public.feedback_id_seq'::regclass);


--
-- Name: golden_dataset_run_cases id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.golden_dataset_run_cases ALTER COLUMN id SET DEFAULT nextval('public.golden_dataset_run_cases_id_seq'::regclass);


--
-- Name: golden_dataset_runs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.golden_dataset_runs ALTER COLUMN id SET DEFAULT nextval('public.golden_dataset_runs_id_seq'::regclass);


--
-- Name: ingestion_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_logs ALTER COLUMN id SET DEFAULT nextval('public.ingestion_logs_id_seq'::regclass);


--
-- Name: legal_relations id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legal_relations ALTER COLUMN id SET DEFAULT nextval('public.legal_relations_id_seq'::regclass);


--
-- Name: messages id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages ALTER COLUMN id SET DEFAULT nextval('public.messages_id_seq'::regclass);


--
-- Name: semantic_cache id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.semantic_cache ALTER COLUMN id SET DEFAULT nextval('public.semantic_cache_id_seq'::regclass);


--
-- Name: alembic_version alembic_version_pkc; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.alembic_version
    ADD CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num);


--
-- Name: chunks chunks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_pkey PRIMARY KEY (id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: documents documents_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.documents
    ADD CONSTRAINT documents_pkey PRIMARY KEY (id);


--
-- Name: feedback feedback_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.feedback
    ADD CONSTRAINT feedback_pkey PRIMARY KEY (id);


--
-- Name: golden_dataset_run_cases golden_dataset_run_cases_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.golden_dataset_run_cases
    ADD CONSTRAINT golden_dataset_run_cases_pkey PRIMARY KEY (id);


--
-- Name: golden_dataset_runs golden_dataset_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.golden_dataset_runs
    ADD CONSTRAINT golden_dataset_runs_pkey PRIMARY KEY (id);


--
-- Name: ingestion_logs ingestion_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_logs
    ADD CONSTRAINT ingestion_logs_pkey PRIMARY KEY (id);


--
-- Name: legal_relations legal_relations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legal_relations
    ADD CONSTRAINT legal_relations_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: semantic_cache semantic_cache_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.semantic_cache
    ADD CONSTRAINT semantic_cache_pkey PRIMARY KEY (id);


--
-- Name: conversations uq_conversations_platform_chat_id; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.conversations
    ADD CONSTRAINT uq_conversations_platform_chat_id UNIQUE (platform, chat_id);


--
-- Name: ix_chunks_document_id; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chunks_document_id ON public.chunks USING btree (document_id);


--
-- Name: ix_chunks_embedding_hnsw_cosine; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX ix_chunks_embedding_hnsw_cosine ON public.chunks USING hnsw (embedding public.vector_cosine_ops);


--
-- Name: chunks chunks_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.chunks
    ADD CONSTRAINT chunks_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE CASCADE;


--
-- Name: feedback feedback_message_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.feedback
    ADD CONSTRAINT feedback_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE CASCADE;


--
-- Name: golden_dataset_run_cases golden_dataset_run_cases_run_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.golden_dataset_run_cases
    ADD CONSTRAINT golden_dataset_run_cases_run_id_fkey FOREIGN KEY (run_id) REFERENCES public.golden_dataset_runs(id) ON DELETE CASCADE;


--
-- Name: ingestion_logs ingestion_logs_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ingestion_logs
    ADD CONSTRAINT ingestion_logs_document_id_fkey FOREIGN KEY (document_id) REFERENCES public.documents(id) ON DELETE SET NULL;


--
-- Name: legal_relations legal_relations_from_chunk_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legal_relations
    ADD CONSTRAINT legal_relations_from_chunk_id_fkey FOREIGN KEY (from_chunk_id) REFERENCES public.chunks(id);


--
-- Name: legal_relations legal_relations_from_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legal_relations
    ADD CONSTRAINT legal_relations_from_document_id_fkey FOREIGN KEY (from_document_id) REFERENCES public.documents(id);


--
-- Name: legal_relations legal_relations_to_document_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legal_relations
    ADD CONSTRAINT legal_relations_to_document_id_fkey FOREIGN KEY (to_document_id) REFERENCES public.documents(id);


--
-- Name: messages messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES public.conversations(id) ON DELETE CASCADE;


--
-- PostgreSQL database dump complete
--

\unrestrict bcb8k9g0z45oufOCKgzHoxK5RHHrhglClHe61fkJ4JiGzoGbgAhHMSXaRBElowg

