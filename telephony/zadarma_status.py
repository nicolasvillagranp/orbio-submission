"""Muestra el estado de tu cuenta de Zadarma sin entrar en la web.

Uso:
    python telephony/zadarma_status.py
"""

import sys

import config  # noqa: F401  (carga el .env)
import zadarma_api

try:
    print(f"Saldo: {zadarma_api.balance()}\n")

    print("Números virtuales:")
    for n in zadarma_api.numbers() or [{}]:
        print(f"  {n.get('number', '(ninguno)')}  {n.get('status', '')}  {n.get('description', '')}")

    print("\nLíneas SIP:")
    for s in zadarma_api.sips():
        print(f"  {s.get('id')}  CallerID: {s.get('display_name') or s.get('callerid') or '(sin asignar)'}")
except zadarma_api.ZadarmaError as e:
    sys.exit(f"Error: {e}")
