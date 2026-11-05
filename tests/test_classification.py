from gmailmcp.classification import TransactionClassifier
from tests.conftest import SETTINGS

classify = TransactionClassifier().classify


def test_bac_con_tarjeta_conocida_es_confianza_alta():
    settings = {"planner": {"cards": [{"name": "AMEX BAC", "last4": "3328"}]}}
    r = classify({"banco": "BAC Credomatic", "tipo": "", "tarjeta_ultimos4": "3328"}, settings)
    assert r == {"cuenta_destino": "AMEX BAC", "last4_destino": "3328",
                 "tipo_clasificado": "compra", "confianza": "alta"}


def test_agricola_transfer365_a_bac():
    r = classify({"banco": "Banco Agrícola", "tipo": "transfer365",
                  "descripcion": "a Banco de America Central"}, SETTINGS)
    assert (r["cuenta_destino"], r["confianza"]) == ("BAC (AMEX/VISA)", "media")


def test_agricola_pago_de_prestamo_usa_el_primer_prestamo():
    r = classify({"banco": "Banco Agrícola", "descripcion": "Pago de préstamo propio"}, SETTINGS)
    assert (r["cuenta_destino"], r["tipo_clasificado"]) == ("Préstamo X", "pago_prestamo")


def test_regla_que_no_resuelve_cae_en_sin_clasificar():
    r = classify({"banco": "Banco Cuscatlán", "tipo": "otro"}, SETTINGS)
    assert r == {"cuenta_destino": None, "last4_destino": None,
                 "tipo_clasificado": "otro", "confianza": "sin_clasificar"}
