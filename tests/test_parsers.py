from gmailmcp.parsers import build_default_registry, get_body_and_attachments
from gmailmcp.parsers.base import BankParser, EmailContent
from gmailmcp.parsers.pdf_statements import AgricolaPdfParser, BacPdfParser
from tests.fakes import make_message


def parse(sender, subject, body):
    return build_default_registry().parse(sender, subject, body)


def test_bac_compra_extrae_tarjeta_comercio_monto_y_fecha():
    r = parse("alertas@baccredomatic.com", "Compra",
              "compra con su tarjeta VISA terminada en 6201\nComercio Monto\nUBER RIDES 9.37 USD\n"
              "2026/10/22-07:24:00\n")
    assert r["tarjeta_ultimos4"] == "6201"
    assert r["comercio"] == "UBER RIDES"
    assert r["monto"] == "9.37"
    assert r["fecha_iso"] == "2026-10-22"
    assert r["tipo"] == "compra"


def test_bac_transferencia_toma_el_monto_en_usd():
    r = parse("notificaciones@baccredomatic.com", "T", "transferencia de 1.00 por USD 50.00")
    assert (r["tipo"], r["monto"]) == ("transferencia", "50.00")


def test_cuscatlan_login_no_tiene_monto():
    r = parse("notificaciones@bancocuscatlan.com", "Inicio de sesión", "sesión iniciada USD 1.00")
    assert r["tipo"] == "login" and r["monto"] == ""


def test_agricola_estado_de_cuenta_extrae_saldo_y_minimo():
    r = parse("notificaciones@notificacionesbancoagricola.com", "Tu Estado de cuenta",
              "XXXX-XXXX-XXXX-6114 Pago mínimo: $81.86 Fecha de corte: 09/10/2026 Saldo actual: $1,133.25")
    assert r["tipo"] == "estado_cuenta_pago_minimo"
    assert (r["monto"], r["saldo"], r["fecha_iso"]) == ("81.86", "1133.25", "2026-10-09")


def test_netflix_sin_monto_devuelve_cadena_vacia():
    assert parse("info@account.netflix.com", "Recibo", "Gracias")["monto"] == ""


def test_remitente_desconocido_usa_el_parser_generico():
    r = parse("alguien@otro.org", "Hola", "Te debo $1,250.50")
    assert (r["banco"], r["monto"]) == ("Desconocido", "1250.50")


def test_registry_se_extiende_sin_modificar_codigo_existente():
    """Open/Closed: un banco nuevo se agrega registrando una clase, sin tocar el registro."""
    class MiBanco(BankParser):
        name = "Mi Banco"
        sender_fragments = ("mibanco.com",)

        def parse(self, email: EmailContent) -> dict:
            return {"banco": self.name, "monto": "1.00"}

    registry = build_default_registry().register(MiBanco())
    assert registry.parse("avisos@mibanco.com", "x", "y") == {"banco": "Mi Banco", "monto": "1.00"}


def test_body_se_decodifica_de_base64():
    body, attachments = get_body_and_attachments(make_message("m1", "a@b", "s", "hola ñ")["payload"])
    assert body == "hola ñ" and attachments == []


def test_pdf_bac_marca_creditos_y_agricola_todo_debito():
    text = "01/10/2026  SUPER  12.50\n03/10/2026  PAGO  100.00 CR\n"
    bac = BacPdfParser().parse(text, "x.pdf")
    assert [(r["fecha_iso"], r["tipo"], r["monto"]) for r in bac] == [
        ("2026-10-01", "debito", "12.50"), ("2026-10-03", "credito", "100.00")]
    assert {r["tipo"] for r in AgricolaPdfParser().parse(text, "x.pdf")} == {"debito"}
