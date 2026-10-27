"""Crea (o reutiliza) el trunk SIP saliente LiveKit -> Zadarma.

Uso:
    python telephony/create_outbound_trunk.py           # crea si no existe
    python telephony/create_outbound_trunk.py --recreate  # borra y vuelve a crear
"""

import argparse
import asyncio
import os

from livekit import api

from config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL, TRUNK_NAME, require


async def find_trunk(lkapi: api.LiveKitAPI):
    resp = await lkapi.sip.list_outbound_trunk(api.ListSIPOutboundTrunkRequest())
    return next((t for t in resp.items if t.name == TRUNK_NAME), None)


async def main(recreate: bool) -> None:
    async with api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) as lkapi:
        existing = await find_trunk(lkapi)
        if existing and not recreate:
            print(f"El trunk ya existe: {existing.sip_trunk_id}")
            return
        if existing:
            await lkapi.sip.delete_trunk(
                api.DeleteSIPTrunkRequest(sip_trunk_id=existing.sip_trunk_id)
            )
            print(f"Trunk anterior borrado: {existing.sip_trunk_id}")

        # Zadarma exige que el remitente sea <login SIP>@sip.zadarma.com (si no,
        # responde 407 en bucle). El número que ve el destinatario es el CallerID
        # configurado en el panel: Configuración -> Conexión SIP -> CallerID.
        server = require("ZADARMA_SIP_SERVER")
        login = require("ZADARMA_SIP_LOGIN")
        # tcp si el router se come las respuestas UDP al puerto 5060 (SIP ALG): el INVITE
        # sale pero Zadarma nunca contesta y la llamada caduca con "sip request timed out".
        transport = (os.getenv("ZADARMA_SIP_TRANSPORT") or "udp").upper()
        trunk = api.SIPOutboundTrunkInfo(
            name=TRUNK_NAME,
            address=server,
            transport=api.SIPTransport.Value(f"SIP_TRANSPORT_{transport}"),
            from_host=server,
            numbers=[login],
            auth_username=login,
            auth_password=require("ZADARMA_SIP_PASSWORD"),
        )
        created = await lkapi.sip.create_outbound_trunk(
            api.CreateSIPOutboundTrunkRequest(trunk=trunk)
        )
        print(f"Trunk creado: {created.sip_trunk_id} ({transport})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--recreate", action="store_true", help="borra y vuelve a crear el trunk")
    asyncio.run(main(parser.parse_args().recreate))
