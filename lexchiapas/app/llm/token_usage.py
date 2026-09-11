"""Acumulador de tokens por-turno (Fase 9.8/A10).

Un turno de RAG dispara VARIAS llamadas LLM: la generacion final mas
auxiliares (decidir, reformular, 2o gate de grounding, query rewriting). Antes
solo se contabilizaban los tokens de la generacion final; los auxiliares se
tiraban (`raw, model_used, _, _ = generate_with_fallback(...)`), subestimando
el costo real ~3-5x.

En vez de enhebrar tuplas de tokens por las 6 firmas auxiliares, se acumula en
el UNICO choke point por el que pasan todas las generaciones
(app.llm.router.generate_with_fallback -> record_usage). El acumulador vive en
un ContextVar por-turno (per-request, seguro ante concurrencia). La atribucion
generacion-vs-auxiliar la marca generate_answer con generation_scope().

Contrato:
- begin_usage()      al inicio del turno (lo llaman los pipelines).
- record_usage(p, c) tras cada llamada LLM exitosa (lo llama el router).
- generation_scope() marca "esta llamada es la generacion principal"
  (lo usa solo generate_answer).
- get_usage()        al final del turno -> (gen_p, gen_c, aux_p, aux_c).

record_usage/generation_scope son no-op seguros si no hubo begin_usage (ej. un
script que llama generate_with_fallback fuera de un turno).
"""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class _Usage:
    gen_prompt: int = 0
    gen_completion: int = 0
    aux_prompt: int = 0
    aux_completion: int = 0


_usage: ContextVar[_Usage | None] = ContextVar("lexchiapas_token_usage", default=None)
_in_generation: ContextVar[bool] = ContextVar("lexchiapas_token_in_generation", default=False)


def begin_usage() -> None:
    """Inicia (o reinicia) el acumulador para el turno actual."""
    _usage.set(_Usage())


def record_usage(prompt_tokens: int | None, completion_tokens: int | None) -> None:
    """Suma los tokens de una llamada LLM al acumulador del turno. Atribuye a
    la cubeta de generacion si estamos dentro de generation_scope(), si no a la
    de auxiliares. No-op si no hay acumulador activo. None cuenta como 0."""
    usage = _usage.get()
    if usage is None:
        return
    p = prompt_tokens or 0
    c = completion_tokens or 0
    if _in_generation.get():
        usage.gen_prompt += p
        usage.gen_completion += c
    else:
        usage.aux_prompt += p
        usage.aux_completion += c


@contextmanager
def generation_scope():
    """Marca las llamadas LLM hechas adentro como generacion principal (no
    auxiliares). Lo usa app.rag.generator.generate_answer alrededor de su
    llamada al router."""
    token = _in_generation.set(True)
    try:
        yield
    finally:
        _in_generation.reset(token)


def get_usage() -> tuple[int, int, int, int]:
    """(gen_prompt, gen_completion, aux_prompt, aux_completion) del turno. Todo
    en 0 si nunca se llamo begin_usage o no hubo llamadas."""
    usage = _usage.get()
    if usage is None:
        return (0, 0, 0, 0)
    return (usage.gen_prompt, usage.gen_completion, usage.aux_prompt, usage.aux_completion)
