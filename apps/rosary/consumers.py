import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer


CLERGY_ROLES = {"religieux", "diacre", "pretre", "eveque", "archeveque"}


class RosaryConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for live community rosary sessions.
    Room group: rosary_{session_id}

    Events (server → client):
      - participant_joined  : {type, user_email, participant_count}
      - decade_advanced     : {type, current_decade}
      - intention_submitted : {type, text, submitted_by}
      - rosary_ended        : {type}

    Client → server messages:
      - advance   (initiator only)
      - submit_intention
      - end       (initiator only)
    """

    async def connect(self):
        self.rosary_id = self.scope["url_route"]["kwargs"]["rosary_id"]
        self.group_name = f"rosary_{self.rosary_id}"
        self.user = self.scope.get("user")

        if not self.user or not self.user.is_authenticated:
            await self.close(code=4001)
            return

        rosary = await self._get_rosary()
        if rosary is None or rosary.status != "active":
            await self.close(code=4004)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        await self._record_participant(rosary)

        count = await self._participant_count()
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "broadcast_participant_joined",
                "user_email": self.user.email,
                "participant_count": count,
            },
        )

    async def disconnect(self, code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        action = data.get("action")

        if action == "advance":
            await self._handle_advance()
        elif action == "submit_intention":
            await self._handle_intention(data.get("text", ""))
        elif action == "end":
            await self._handle_end()

    # ── Handlers ──────────────────────────────────────────────────────────────

    async def _handle_advance(self):
        rosary = await self._get_rosary()
        if rosary is None or rosary.initiator_id != self.user.pk:
            return
        new_decade = await self._advance_decade(rosary)
        await self.channel_layer.group_send(
            self.group_name,
            {"type": "broadcast_decade_advanced", "current_decade": new_decade},
        )

    async def _handle_intention(self, text: str):
        if not text.strip():
            return
        await self._save_intention(text)
        await self.channel_layer.group_send(
            self.group_name,
            {
                "type": "broadcast_intention_submitted",
                "text": text,
                "submitted_by": self.user.email,
            },
        )

    async def _handle_end(self):
        rosary = await self._get_rosary()
        if rosary is None or rosary.initiator_id != self.user.pk:
            return
        await self._end_rosary(rosary)
        await self.channel_layer.group_send(
            self.group_name, {"type": "broadcast_rosary_ended"}
        )

    # ── Broadcast handlers (called by channel layer) ───────────────────────

    async def broadcast_participant_joined(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "participant_joined",
                    "user_email": event["user_email"],
                    "participant_count": event["participant_count"],
                }
            )
        )

    async def broadcast_decade_advanced(self, event):
        await self.send(
            text_data=json.dumps(
                {"type": "decade_advanced", "current_decade": event["current_decade"]}
            )
        )

    async def broadcast_intention_submitted(self, event):
        await self.send(
            text_data=json.dumps(
                {
                    "type": "intention_submitted",
                    "text": event["text"],
                    "submitted_by": event["submitted_by"],
                }
            )
        )

    async def broadcast_rosary_ended(self, event):
        await self.send(text_data=json.dumps({"type": "rosary_ended"}))

    # ── DB helpers ─────────────────────────────────────────────────────────

    @database_sync_to_async
    def _get_rosary(self):
        from apps.rosary.models import CommunityRosary

        try:
            return CommunityRosary.objects.get(pk=self.rosary_id)
        except CommunityRosary.DoesNotExist:
            return None

    @database_sync_to_async
    def _record_participant(self, rosary):
        from apps.rosary.models import RosaryParticipant

        RosaryParticipant.objects.get_or_create(rosary=rosary, user=self.user)

    @database_sync_to_async
    def _participant_count(self) -> int:
        from apps.rosary.models import RosaryParticipant

        return RosaryParticipant.objects.filter(rosary_id=self.rosary_id).count()

    @database_sync_to_async
    def _advance_decade(self, rosary) -> int:
        rosary.current_decade += 1
        rosary.save(update_fields=["current_decade", "updated_at"])
        return rosary.current_decade

    @database_sync_to_async
    def _save_intention(self, text: str):
        from apps.rosary.models import CommunityRosary, RosaryIntention

        try:
            rosary = CommunityRosary.objects.get(pk=self.rosary_id, status="active")
            RosaryIntention.objects.create(rosary=rosary, submitted_by=self.user, text=text)
        except CommunityRosary.DoesNotExist:
            pass

    @database_sync_to_async
    def _end_rosary(self, rosary):
        from django.utils import timezone

        rosary.status = "completed"
        rosary.ended_at = timezone.now()
        rosary.save(update_fields=["status", "ended_at", "updated_at"])
