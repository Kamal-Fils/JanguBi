"""Trames temps réel du chapelet communautaire — **définition unique**.

Le consumer WebSocket (``apps.rosary.consumers``) et les services HTTP
(``apps.rosary.community_services``) doivent émettre exactement les mêmes trames
sur exactement le même groupe. Ce module en est l'unique source : une trame se
modifie ICI et nulle part ailleurs.

Pourquoi : les endpoints REST persistaient sans diffuser. Quand l'initiateur
clôturait la session socket coupé, ``rosary_ended`` n'atteignait jamais les
autres participants — bloqués devant une session morte jusqu'au rechargement.

Contrat client (``JanguBiUI/src/features/chapelet/hooks/use-community-rosary-socket.ts``) :
les quatre trames historiques sont parsées par un ``z.discriminatedUnion`` strict.
**Ne jamais renommer ni retirer une clé** — seules des trames NOUVELLES peuvent
être ajoutées (le front ignore proprement ce qu'il ne connaît pas).
"""

from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

# Clé d'enveloppe côté channel layer : nomme la méthode du consumer qui reçoit
# l'événement. Interne serveur↔serveur, invisible du client.
BROADCAST_HANDLER = "rosary_broadcast"


def rosary_group_name(rosary_id: int | str) -> str:
    """Nom du groupe channel layer d'une session. Unique définition."""
    return f"rosary_{rosary_id}"


# ── Trames serveur → client ────────────────────────────────────────────────
# Historiques (consommées par le front) : ne pas toucher.


def participant_joined_frame(*, user_email: str, participant_count: int) -> dict[str, Any]:
    return {
        "type": "participant_joined",
        "user_email": user_email,
        "participant_count": participant_count,
    }


def decade_advanced_frame(*, current_decade: int) -> dict[str, Any]:
    return {"type": "decade_advanced", "current_decade": current_decade}


def intention_submitted_frame(*, text: str, submitted_by: str) -> dict[str, Any]:
    return {"type": "intention_submitted", "text": text, "submitted_by": submitted_by}


def rosary_ended_frame() -> dict[str, Any]:
    return {"type": "rosary_ended"}


# Nouvelles trames — additives, jamais diffusées au groupe : elles s'adressent
# au seul socket concerné.


def session_state_frame(
    *,
    participants: list[dict[str, Any]],
    participant_count: int,
    current_decade: int,
    status: str,
    initiator_email: str | None,
    is_initiator: bool,
) -> dict[str, Any]:
    """État initial envoyé au socket qui vient de se connecter.

    Sans elle, la liste nominative des participants ne contient que les arrivées
    observées depuis la connexion : le compteur était juste, la liste non.
    """
    return {
        "type": "session_state",
        "participants": participants,
        "participant_count": participant_count,
        "current_decade": current_decade,
        "status": status,
        "initiator_email": initiator_email,
        "is_initiator": is_initiator,
    }


def action_rejected_frame(*, action: str, reason: str) -> dict[str, Any]:
    """Refus explicite d'une action client.

    ``advance``/``end`` étaient silencieusement ignorés hors initiateur : le
    client ne distinguait pas « refusé » de « perdu ».
    """
    return {"type": "action_rejected", "action": action, "reason": reason}


# ── Diffusion ──────────────────────────────────────────────────────────────


def _envelope(frame: dict[str, Any]) -> dict[str, Any]:
    return {"type": BROADCAST_HANDLER, "frame": frame}


def broadcast_frame_sync(*, rosary_id: int | str, frame: dict[str, Any]) -> None:
    """Diffuse depuis un contexte **synchrone** (service Django, tâche Celery).

    Sans channel layer configuré (tests unitaires, commande de gestion), la
    diffusion est un no-op : la persistance ne doit jamais échouer à cause du
    transport temps réel.
    """
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(rosary_group_name(rosary_id), _envelope(frame))


async def broadcast_frame_async(*, rosary_id: int | str, frame: dict[str, Any]) -> None:
    """Diffuse depuis un contexte **asynchrone** (consumer WebSocket)."""
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    await channel_layer.group_send(rosary_group_name(rosary_id), _envelope(frame))
