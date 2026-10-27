"""Llamadas salientes: LiveKit crea la sala y Zadarma marca el número.

Uso desde código:
    import asyncio
    from calls import start_call

    call = asyncio.run(start_call("+34600111222"))                         # solo llamada
    call = asyncio.run(start_call("+34600111222", agent="zadarma-agent"))  # con agente
"""

import asyncio
import json
import os
import time
from dataclasses import dataclass

from livekit import api

from config import LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL, TRUNK_NAME
import number_pool
import zadarma_api
from create_outbound_trunk import find_trunk


class CallError(Exception):
    """La llamada no se pudo establecer (incluye el código SIP si lo hay)."""

    def __init__(self, message: str, sip_status: str | None = None):
        super().__init__(f"{message} (SIP {sip_status})" if sip_status else message)
        self.sip_status = sip_status


@dataclass
class Call:
    room: str
    phone_number: str
    participant_identity: str
    agent: str | None


def room_name_for(phone_number: str) -> str:
    digits = "".join(c for c in phone_number if c.isdigit())
    return f"call-{digits}-{int(time.time())}"


async def start_call(
    phone_number: str,
    *,
    agent: str | None = None,
    room: str | None = None,
    caller_id: str | None = None,
    wait_until_answered: bool = True,
    record: bool = False,
) -> Call:
    """Crea la sala, despacha el agente (opcional) y llama a `phone_number`.

    `caller_id` (por defecto ZADARMA_CALLER_ID del .env) es el número que verá el
    destinatario. Se aplica con la API de Zadarma antes de marcar; tiene que ser
    un número tuyo y activo. Con "auto" se elige al azar uno libre (que ninguna
    llamada abierta esté usando) entre tus números activos; ver number_pool.py. Ojo: el CallerID es de la línea SIP, no de la
    llamada, así que dos llamadas simultáneas comparten el último que se puso.

    Con `record=True` (desactivado por defecto) se graba el audio de la sala (los dos lados) en
    infra/livekit/recordings/<sala>.ogg mediante el servicio egress. Si egress no
    está corriendo, se avisa y la llamada sigue sin grabarse.

    Si `agent` está indicado pero ese agente aún no está corriendo, el dispatch
    queda pendiente y la llamada funciona igual: el agente entrará cuando exista.
    """
    room = room or room_name_for(phone_number)
    identity = f"tel-{phone_number}"

    caller_id = caller_id or os.getenv("ZADARMA_CALLER_ID")

    async with api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) as lkapi:
        trunk = await find_trunk(lkapi)
        if not trunk:
            raise CallError(f"No existe el trunk '{TRUNK_NAME}'. Ejecuta create_outbound_trunk.py")

        # 0. CallerID: el indicado, o "auto" = uno libre al azar entre tus números.
        if caller_id and not zadarma_api.is_configured():
            print(f"Aviso: sin ZADARMA_API_KEY/SECRET no puedo poner el CallerID {caller_id}; "
                  "se usará el que tenga la línea en el panel.")
            caller_id = None
        elif caller_id:
            try:
                if caller_id == "auto":
                    caller_id = await number_pool.pick(lkapi)
                    print(f"CallerID elegido: {caller_id}")
                await asyncio.to_thread(
                    zadarma_api.set_caller_id, os.environ["ZADARMA_SIP_LOGIN"], caller_id
                )
            except zadarma_api.ZadarmaError as e:
                raise CallError(f"No se pudo poner el CallerID {caller_id}: {e}") from e
        metadata = json.dumps({"phone_number": phone_number, "caller_id": caller_id})

        # 1. El "entorno" de la llamada: una sala que se cierra sola al colgar.
        await lkapi.room.create_room(
            api.CreateRoomRequest(name=room, empty_timeout=300, departure_timeout=20, metadata=metadata)
        )
        # Si la sala ya existía (--listen), create_room no pisa su metadata.
        await lkapi.room.update_room_metadata(
            api.UpdateRoomMetadataRequest(room=room, metadata=metadata)
        )

        # 1b. Grabación: se arranca antes de marcar para no perder el principio.
        if record:
            await _start_recording(lkapi, room)

        # 2. Agente opcional: se despacha antes de marcar para que esté listo al descolgar.
        if agent:
            await lkapi.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(agent_name=agent, room=room, metadata=metadata)
            )

        # 3. Zadarma marca el número y el teléfono entra en la sala como participante.
        try:
            await lkapi.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    sip_trunk_id=trunk.sip_trunk_id,
                    # Con "+": sin él, Zadarma toma el número como nacional y antepone
                    # otro 34 (34600... -> 3434600...), y la llamada falla con 503.
                    sip_call_to=phone_number,
                    room_name=room,
                    participant_identity=identity,
                    participant_name=f"Teléfono {phone_number}",
                    wait_until_answered=wait_until_answered,
                )
            )
        except api.TwirpError as e:
            await lkapi.room.delete_room(api.DeleteRoomRequest(room=room))
            raise CallError(e.message, (e.metadata or {}).get("sip_status_code")) from e

    return Call(room=room, phone_number=phone_number, participant_identity=identity, agent=agent)


async def _start_recording(lkapi: api.LiveKitAPI, room: str) -> None:
    try:
        await lkapi.egress.start_room_composite_egress(
            api.RoomCompositeEgressRequest(
                room_name=room,
                audio_only=True,
                file_outputs=[
                    api.EncodedFileOutput(
                        file_type=api.EncodedFileType.OGG, filepath=f"/out/{room}.ogg"
                    )
                ],
            )
        )
    except api.TwirpError as e:
        print(f"Aviso: no se pudo iniciar la grabación ({e.message}). ¿Está el servicio egress levantado?")


async def wait_for_listener(room: str) -> None:
    """Crea la sala y espera a que alguien entre (p. ej. tú desde el navegador)."""
    async with api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) as lkapi:
        await lkapi.room.create_room(api.CreateRoomRequest(name=room, empty_timeout=300))
        while True:
            resp = await lkapi.room.list_participants(api.ListParticipantsRequest(room=room))
            if resp.participants:
                return
            await asyncio.sleep(1)


async def is_active(call: Call) -> bool:
    """True mientras el teléfono siga en la sala (es decir, sin colgar)."""
    async with api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) as lkapi:
        resp = await lkapi.room.list_participants(api.ListParticipantsRequest(room=call.room))
    return any(p.identity == call.participant_identity for p in resp.participants)


async def hang_up(room: str | None = None) -> list[str]:
    """Cuelga borrando la sala. Sin `room`, cuelga todas las llamadas abiertas."""
    async with api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) as lkapi:
        if room:
            rooms = [room]
        else:
            resp = await lkapi.room.list_rooms(api.ListRoomsRequest())
            rooms = [r.name for r in resp.rooms if r.name.startswith("call-")]
        for name in rooms:
            try:
                await lkapi.room.delete_room(api.DeleteRoomRequest(room=name))
            except api.TwirpError as e:
                if e.code != "not_found":  # la sala ya se cerró sola al colgar
                    raise
    return rooms
