"""Cliente mínimo de la API REST de Zadarma (https://zadarma.com/es/support/api/).

Las claves se generan una vez en el panel: Configuración -> API y webhooks.
La firma replica la librería oficial (github.com/zadarma/user-api-py-v1).
"""

import base64
import hashlib
import hmac
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request

import certifi

API_URL = "https://api.zadarma.com"
# El Python de python.org en macOS no trae certificados raíz; usamos los de certifi.
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class ZadarmaError(Exception):
    pass


def is_configured() -> bool:
    return bool(os.getenv("ZADARMA_API_KEY") and os.getenv("ZADARMA_API_SECRET"))


def call(method: str, params: dict | None = None, http: str = "GET") -> dict:
    """Llama a un método de la API, p. ej. call("/v1/info/balance/")."""
    key, secret = os.getenv("ZADARMA_API_KEY"), os.getenv("ZADARMA_API_SECRET")
    if not (key and secret):
        raise ZadarmaError("Faltan ZADARMA_API_KEY / ZADARMA_API_SECRET en .env")

    params = {**(params or {}), "format": "json"}
    query = urllib.parse.urlencode(sorted(params.items()))
    to_sign = method + query + hashlib.md5(query.encode()).hexdigest()
    digest = hmac.new(secret.encode(), to_sign.encode(), hashlib.sha1).hexdigest()
    auth = f"{key}:{base64.b64encode(digest.encode()).decode()}"

    url = API_URL + method
    body = None
    if http == "GET":
        url += "?" + query
    else:
        body = query.encode()
    request = urllib.request.Request(url, data=body, method=http, headers={"Authorization": auth})
    try:
        with urllib.request.urlopen(request, timeout=15, context=SSL_CONTEXT) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        data = json.loads(e.read() or b"{}")

    if data.get("status") != "success":
        raise ZadarmaError(data.get("message") or f"Error de la API de Zadarma: {data}")
    return data


def balance() -> str:
    data = call("/v1/info/balance/")
    return f"{data['balance']} {data['currency']}"


def numbers() -> list[dict]:
    """Números virtuales de la cuenta (con su estado)."""
    return call("/v1/direct_numbers/").get("info", [])


def sips() -> list[dict]:
    """Líneas SIP de la cuenta (con su CallerID actual)."""
    return call("/v1/sip/").get("sips", [])


def set_caller_id(sip: str, number: str) -> None:
    """Cambia el número que se muestra al llamar desde la línea `sip`.

    `number` debe ser un número tuyo y activo en Zadarma.
    """
    digits = "".join(c for c in number if c.isdigit())
    call("/v1/sip/callerid/", {"id": sip, "number": digits}, http="PUT")
