from app.rag.vigencia import is_articulo_derogado


def test_articulo_completamente_derogado_sin_marcador():
    assert is_articulo_derogado("Articulo 150.- Se Deroga.") is True


def test_articulo_completamente_derogado_con_marcador_periodico_oficial():
    content = (
        "Articulo 211.- Se Deroga\n"
        "(DEROGACION PUBLICADA MEDIANTE P.O. NUM. 187 2A. SECCION DE FECHA "
        "01 DE JULIO DE 2015)"
    )
    assert is_articulo_derogado(content) is True


def test_articulo_derogado_con_acento_y_multiples_marcadores():
    content = (
        "Artículo 214.- Se Deroga.\n"
        "(REFORMADO MEDIANTE P.O. NUM. 113 DE FECHA 28 DE AGOSTO 2008)\n"
        "(DEROGACION PUBLICADA MEDIANTE P.O. NUM. 187 2A. SECCION DE FECHA "
        "01 DE JULIO DE 2015)"
    )
    assert is_articulo_derogado(content) is True


def test_articulo_normal_no_se_marca_derogado():
    content = (
        "Articulo 270.- Comete el delito de robo, el que se apodere de una "
        "cosa mueble ajena, sin derecho y sin el consentimiento de quien "
        "legalmente pueda otorgarlo."
    )
    assert is_articulo_derogado(content) is False


def test_derogacion_parcial_de_una_fraccion_no_se_marca_como_articulo_completo():
    # Solo una fraccion se derogo, el articulo sigue vigente en lo demas --
    # NO debe marcarse como derogado (ver docstring del modulo, limitacion
    # deliberada).
    content = (
        "IX.Congreso del Estado: Al Honorable Congreso del Estado de Chiapas.\n"
        "(SE DEROGA MEDIANTE P. O. NUM 274 DE FECHA 31 DE DICIEMBRE DE 2016)\n"
        "X. Otra fraccion que sigue vigente y describe algo mas."
    )
    assert is_articulo_derogado(content) is False


def test_articulo_derogado_sin_punto_final():
    assert is_articulo_derogado("Articulo 75.- Se deroga") is True
