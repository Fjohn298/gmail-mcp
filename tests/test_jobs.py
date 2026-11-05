import base64
import email

from gmailmcp.services.payment_planner import build_plan, period_label, planner_config
from tests.conftest import SETTINGS
from tests.fakes import make_message


def test_cleanup_no_entra_en_bucle_con_hilos_protegidos(container, gmail):
    """Regresión: un hilo de spam con etiqueta protegida se repetía para siempre."""
    gmail.add(make_message("p1", "promo@spam.com", "s", "b", labels=("INBOX", "Label_3")),
              make_message("s1", "ofertas@spam.com", "s", "b"),
              make_message("s2", "mas@spam.com", "s", "b"),
              make_message("ok", "amigo@otro.com", "s", "b"))
    assert container.cleanup_service().run() == 2
    assert gmail.trashed == {"s1", "s2"}


def test_labeler_etiqueta_por_remitente_y_deja_una_sola_etiqueta(container, gmail):
    gmail.add(make_message("a", "BAC <alertas@baccredomatic.com>", "s", "b"),
              make_message("b", "team@datacamp.com", "s", "b", labels=("INBOX", "Label_3", "Label_2")))
    assert container.labeler_service().run() == 1
    assert "Label_3" in gmail.msgs["a"]["labelIds"]
    assert gmail.msgs["b"]["labelIds"] == ["INBOX", "Label_3"]   # Recibos tiene prioridad sobre Cursos


def test_extractor_guarda_movimientos_omite_logins_y_no_duplica(container, gmail):
    gmail.add(make_message("t1", "alertas@baccredomatic.com", "Compra",
                           "compra Comercio Monto\nSUPER 12.50 USD\n", labels=("INBOX", "Label_3")),
              make_message("t2", "notificaciones@bancocuscatlan.com", "Inicio de sesión", "sesión",
                           labels=("INBOX", "Label_3")))
    assert container.extractor_service().run() == 1
    assert container.extractor_service().run() == 0              # segunda corrida: dedup por message_id
    rows = container.transactions.all()
    assert [(r["message_id"], r["monto"], r["fuente"]) for r in rows] == [("t1", "12.50", "email")]


def test_plan_prioriza_la_tarjeta_de_mayor_tasa():
    plan = build_plan(planner_config(SETTINGS))
    assert plan["savings"] == 50.0
    assert [p["last4"] for p in plan["payments"]] == ["1111", "2222"]
    assert plan["payments"][0]["is_focus"] is True
    assert plan["total_prestamos"] == 25.0


def test_build_plan_sin_salario_devuelve_none():
    assert build_plan({"salary_per_period": 0}) is None


def test_period_label():
    from datetime import datetime
    assert period_label(datetime(2026, 11, 4)) == "Quincena del 15 de noviembre 2026"
    assert period_label(datetime(2026, 11, 28)) == "Quincena del 30 de noviembre 2026"


def test_resumen_diario_se_envia_al_correo_configurado(container, gmail):
    container.summary_service().send()
    msg = email.message_from_bytes(base64.urlsafe_b64decode(gmail.sent[0] + "=="))
    assert msg["To"] == "yo@example.com"
