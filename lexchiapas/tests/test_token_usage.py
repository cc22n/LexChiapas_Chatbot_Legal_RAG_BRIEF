"""Acumulador de tokens por-turno (Fase 9.8/A10).

Verifica la atribucion generacion-vs-auxiliar y que sea no-op seguro fuera de
un turno (sin begin_usage)."""

from app.llm.token_usage import begin_usage, generation_scope, get_usage, record_usage


def test_no_op_without_begin():
    # Sin begin_usage (ej. un script que usa generate_with_fallback), record
    # no debe acumular nada ni fallar.
    record_usage(100, 50)
    assert get_usage() == (0, 0, 0, 0)


def test_records_auxiliary_by_default():
    begin_usage()
    record_usage(30, 10)  # fuera de generation_scope -> auxiliar
    assert get_usage() == (0, 0, 30, 10)


def test_records_generation_inside_scope():
    begin_usage()
    with generation_scope():
        record_usage(200, 80)  # generacion principal
    assert get_usage() == (200, 80, 0, 0)


def test_accumulates_mixed_calls_across_the_turn():
    begin_usage()
    record_usage(10, 5)  # aux (decidir)
    record_usage(12, 6)  # aux (grounding)
    with generation_scope():
        record_usage(300, 120)  # generacion
    gen_p, gen_c, aux_p, aux_c = get_usage()
    assert (gen_p, gen_c) == (300, 120)
    assert (aux_p, aux_c) == (22, 11)


def test_none_tokens_count_as_zero():
    begin_usage()
    record_usage(None, None)
    with generation_scope():
        record_usage(None, 40)
    assert get_usage() == (0, 40, 0, 0)


def test_begin_usage_resets_previous_turn():
    begin_usage()
    record_usage(99, 99)
    begin_usage()  # nuevo turno
    assert get_usage() == (0, 0, 0, 0)
