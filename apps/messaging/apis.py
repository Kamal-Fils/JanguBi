from uuid import UUID

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.mixins import ApiAuthMixin
from apps.core.exceptions import ApplicationError
from apps.messaging.models import Conversation, Message, MessageBlock, PriestProfile
from apps.messaging.permissions import (
    HasAcceptedMessagingCgu,
    IsBlockOwner,
    IsMessageSender,
    IsParticipant,
    IsPriestProfileOwner,
)
from apps.messaging.selectors import (
    block_list,
    conversation_list,
    export_list,
    message_list,
    notification_list,
    priest_list_available,
)
from apps.messaging.serializers import (
    BlockCreateInputSerializer,
    BlockOutputSerializer,
    ConversationCreateInputSerializer,
    ConversationOutputSerializer,
    ExportOutputSerializer,
    MessageListInputSerializer,
    MessageOutputSerializer,
    MessageSendInputSerializer,
    NotificationOutputSerializer,
    PriestProfileCreateInputSerializer,
    PriestProfileOutputSerializer,
    PriestProfileUpdateInputSerializer,
    ReactInputSerializer,
)
from apps.messaging.services import (
    block_user,
    conversation_accept_cgu,
    conversation_archive,
    conversation_delete,
    conversation_export_request,
    conversation_get_or_create,
    message_delete,
    message_mark_read,
    message_react,
    message_send,
    message_unreact,
    notification_mark_read,
    priest_profile_accept_cgu,
    priest_profile_create,
    priest_profile_update,
    unblock_user,
)
from apps.users.models import BaseUser
from apps.users.permissions import IsAnyAdmin


def _error(exc: ApplicationError) -> Response:
    return Response({"detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# PriestProfile
# ---------------------------------------------------------------------------


class PriestProfileCreateApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsAnyAdmin]

    @extend_schema(request=PriestProfileCreateInputSerializer, responses={201: PriestProfileOutputSerializer})
    def post(self, request):
        serializer = PriestProfileCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = get_object_or_404(BaseUser, id=serializer.validated_data["user_id"])
        try:
            profile = priest_profile_create(user=user, accepted_by=request.user)
        except ApplicationError as exc:
            return _error(exc)
        return Response(PriestProfileOutputSerializer(profile).data, status=status.HTTP_201_CREATED)


class PriestProfileCguApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsPriestProfileOwner]

    @extend_schema(responses={200: PriestProfileOutputSerializer})
    def post(self, request):
        try:
            profile = priest_profile_accept_cgu(priest_profile=request.user.priest_profile)
        except ApplicationError as exc:
            return _error(exc)
        return Response(PriestProfileOutputSerializer(profile).data)


class PriestProfileUpdateApi(ApiAuthMixin, APIView):
    permission_classes = [IsAuthenticated, IsPriestProfileOwner]

    @extend_schema(request=PriestProfileUpdateInputSerializer, responses={200: PriestProfileOutputSerializer})
    def patch(self, request):
        serializer = PriestProfileUpdateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = priest_profile_update(
            priest_profile=request.user.priest_profile, **serializer.validated_data
        )
        return Response(PriestProfileOutputSerializer(profile).data)


class PriestListApi(ApiAuthMixin, APIView):
    @extend_schema(responses={200: PriestProfileOutputSerializer(many=True)})
    def get(self, request):
        priests = priest_list_available()
        return Response(PriestProfileOutputSerializer(priests, many=True).data)


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


class ConversationListApi(ApiAuthMixin, APIView):
    @extend_schema(responses={200: ConversationOutputSerializer(many=True)})
    def get(self, request):
        conversations = conversation_list(user=request.user)
        return Response(ConversationOutputSerializer(conversations, many=True).data)


class ConversationCreateApi(ApiAuthMixin, APIView):
    @extend_schema(request=ConversationCreateInputSerializer, responses={201: ConversationOutputSerializer})
    def post(self, request):
        serializer = ConversationCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        priest_user = get_object_or_404(BaseUser, id=serializer.validated_data["priest_user_id"])
        conversation, _ = conversation_get_or_create(fidele=request.user, priest=priest_user)
        return Response(ConversationOutputSerializer(conversation).data, status=status.HTTP_201_CREATED)


class ConversationCguApi(ApiAuthMixin, APIView):
    def get_permissions(self):
        return [IsAuthenticated(), IsParticipant()]

    @extend_schema(responses={200: ConversationOutputSerializer})
    def post(self, request, conversation_id: UUID):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        self.check_object_permissions(request, conversation)
        try:
            conversation = conversation_accept_cgu(conversation=conversation, user=request.user)
        except ApplicationError as exc:
            return _error(exc)
        return Response(ConversationOutputSerializer(conversation).data)


class ConversationArchiveApi(ApiAuthMixin, APIView):
    def get_permissions(self):
        return [IsAuthenticated(), IsParticipant()]

    @extend_schema(responses={200: ConversationOutputSerializer})
    def post(self, request, conversation_id: UUID):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        self.check_object_permissions(request, conversation)
        conversation = conversation_archive(conversation=conversation, user=request.user)
        return Response(ConversationOutputSerializer(conversation).data)


class ConversationDeleteApi(ApiAuthMixin, APIView):
    def get_permissions(self):
        return [IsAuthenticated(), IsParticipant()]

    @extend_schema(responses={204: None})
    def delete(self, request, conversation_id: UUID):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        self.check_object_permissions(request, conversation)
        conversation_delete(conversation=conversation, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConversationExportApi(ApiAuthMixin, APIView):
    def get_permissions(self):
        return [IsAuthenticated(), IsParticipant()]

    @extend_schema(responses={201: ExportOutputSerializer})
    def post(self, request, conversation_id: UUID):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        self.check_object_permissions(request, conversation)
        export = conversation_export_request(conversation=conversation, user=request.user)
        return Response(ExportOutputSerializer(export).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: ExportOutputSerializer(many=True)})
    def get(self, request, conversation_id: UUID):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        self.check_object_permissions(request, conversation)
        exports = export_list(conversation=conversation)
        return Response(ExportOutputSerializer(exports, many=True).data)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class MessageListApi(ApiAuthMixin, APIView):
    def get_permissions(self):
        return [IsAuthenticated(), IsParticipant(), HasAcceptedMessagingCgu()]

    @extend_schema(parameters=[MessageListInputSerializer], responses={200: MessageOutputSerializer(many=True)})
    def get(self, request, conversation_id: UUID):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        self.check_object_permissions(request, conversation)
        input_serializer = MessageListInputSerializer(data=request.query_params)
        input_serializer.is_valid(raise_exception=True)
        messages = message_list(conversation=conversation, **input_serializer.validated_data)
        return Response(MessageOutputSerializer(messages, many=True).data)


class MessageSendApi(ApiAuthMixin, APIView):
    def get_permissions(self):
        return [IsAuthenticated(), IsParticipant(), HasAcceptedMessagingCgu()]

    @extend_schema(request=MessageSendInputSerializer, responses={201: MessageOutputSerializer})
    def post(self, request, conversation_id: UUID):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        self.check_object_permissions(request, conversation)
        serializer = MessageSendInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reply_to = None
        reply_to_id = serializer.validated_data.get("reply_to_id")
        if reply_to_id:
            reply_to = get_object_or_404(Message, id=reply_to_id, conversation=conversation)

        try:
            message = message_send(
                conversation=conversation,
                sender=request.user,
                content=serializer.validated_data["content"],
                client_message_id=serializer.validated_data.get("client_message_id"),
                reply_to=reply_to,
            )
        except ApplicationError as exc:
            return _error(exc)
        return Response(MessageOutputSerializer(message).data, status=status.HTTP_201_CREATED)


class MessageReadApi(ApiAuthMixin, APIView):
    def get_permissions(self):
        return [IsAuthenticated(), IsParticipant()]

    @extend_schema(responses={200: None})
    def post(self, request, conversation_id: UUID):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        self.check_object_permissions(request, conversation)
        message_mark_read(conversation=conversation, reader=request.user)
        return Response({"status": "ok"})


class MessageDeleteApi(ApiAuthMixin, APIView):
    def get_permissions(self):
        return [IsAuthenticated(), IsMessageSender()]

    @extend_schema(responses={204: None})
    def delete(self, request, message_id: UUID):
        message = get_object_or_404(Message, id=message_id)
        self.check_object_permissions(request, message)
        try:
            message_delete(message=message, user=request.user)
        except ApplicationError as exc:
            return _error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageReactApi(ApiAuthMixin, APIView):
    @extend_schema(request=ReactInputSerializer, responses={201: None})
    def post(self, request, message_id: UUID):
        message = get_object_or_404(Message, id=message_id)
        serializer = ReactInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message_react(message=message, user=request.user, emoji=serializer.validated_data["emoji"])
        return Response(status=status.HTTP_201_CREATED)

    @extend_schema(request=ReactInputSerializer, responses={204: None})
    def delete(self, request, message_id: UUID):
        message = get_object_or_404(Message, id=message_id)
        serializer = ReactInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        message_unreact(message=message, user=request.user, emoji=serializer.validated_data["emoji"])
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


class BlockListCreateApi(ApiAuthMixin, APIView):
    @extend_schema(responses={200: BlockOutputSerializer(many=True)})
    def get(self, request):
        blocks = block_list(user=request.user)
        return Response(BlockOutputSerializer(blocks, many=True).data)

    @extend_schema(request=BlockCreateInputSerializer, responses={201: BlockOutputSerializer})
    def post(self, request):
        serializer = BlockCreateInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        blocked_user = get_object_or_404(BaseUser, id=serializer.validated_data["blocked_user_id"])
        try:
            block = block_user(blocker=request.user, blocked=blocked_user)
        except ApplicationError as exc:
            return _error(exc)
        return Response(BlockOutputSerializer(block).data, status=status.HTTP_201_CREATED)


class BlockDeleteApi(ApiAuthMixin, APIView):
    def get_permissions(self):
        return [IsAuthenticated(), IsBlockOwner()]

    @extend_schema(responses={204: None})
    def delete(self, request, block_id: UUID):
        block = get_object_or_404(MessageBlock, id=block_id)
        self.check_object_permissions(request, block)
        try:
            unblock_user(blocker=request.user, blocked=block.blocked)
        except ApplicationError as exc:
            return _error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------------


class NotificationListApi(ApiAuthMixin, APIView):
    @extend_schema(responses={200: NotificationOutputSerializer(many=True)})
    def get(self, request):
        unread_only = request.query_params.get("unread_only", "false").lower() == "true"
        notifications = notification_list(user=request.user, unread_only=unread_only)
        return Response(NotificationOutputSerializer(notifications, many=True).data)


class NotificationReadApi(ApiAuthMixin, APIView):
    @extend_schema(responses={200: NotificationOutputSerializer})
    def post(self, request, notification_id: UUID):
        from apps.messaging.models import Notification

        notification = get_object_or_404(Notification, id=notification_id)
        try:
            notification = notification_mark_read(notification=notification, user=request.user)
        except ApplicationError as exc:
            return _error(exc)
        return Response(NotificationOutputSerializer(notification).data)
