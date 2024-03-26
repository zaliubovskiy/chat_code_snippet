import json
from typing import Any

from choices import ProfileTypes, UserTypes
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import DateTimeField, Exists, F, OuterRef, Subquery
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from django.http import HttpRequest, JsonResponse
from django.shortcuts import get_object_or_404
from login.app_permissions import CustomPermission1, CustomPermission2, CustomPermission3, CustomPermission4
from rest_framework import generics, parsers, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from chat.models import Attachment, Chat, Message
from chat.serializers import (
    ChatAttachmentSerializer,
    ChatDeleteSerializer,
    ContactUserSerializer,
    MarkMessagesAsViewedSerializer,
)

User = get_user_model()


class ChatListView(generics.ListAPIView):
    permission_classes: tuple = (CustomPermission2,)

    def get_queryset(self):
        """
        Overrides the default get_queryset method to return a queryset of Chat instances.
        Returns a queryset of Chat instances that are not deleted, sorted by the latest message time or creation time.
        """
        latest_message_times = Message.objects.filter(
            chat=OuterRef("pk")
        ).order_by("-created_at").values("created_at")[:1]

        # Annotate and filter chats based on user type
        chats = Chat.objects.filter(
            is_deleted=False, participants=self.request.user
        ).annotate(
            sorting_time=Coalesce(Subquery(latest_message_times, output_field=DateTimeField()), F("created_at"))
        )

        # TODO: Implement this via URL query parameters
        if self.request.user.user_type == UserTypes.ADMIN:
            chats = self.filter_for_admin(chats)
        elif self.request.user.user_type == UserTypes.PARENT:
            chats = self.filter_for_parent(chats)

        return chats.order_by("-sorting_time")

    def filter_for_admin(self, chats):
        """
        Filters chats for admin users to include only those where the other participant has completed registration.
        """
        other_participant_completed_registration = User.objects.filter(
            chats=OuterRef("pk"),
            user__is_completed_registration=True
        ).exclude(pk=self.request.user.pk)

        return chats.annotate(
            partner_completed_registration=Exists(other_participant_completed_registration)
        ).filter(partner_completed_registration=True)

    def filter_for_parent(self, chats):
        """
        Filters chats for parent users based on profile ID.
        """
        return chats.filter(profile_id=self.kwargs.get("pk"))

    def list(self, request, *args, **kwargs) -> Response:
        queryset = self.filter_queryset(self.get_queryset())
        participants_info, chats_info = self.organize_chats(queryset)
        response_data = self.prepare_response(participants_info, chats_info)
        return Response(response_data)

    def organize_chats(self, queryset) -> tuple[dict[int, dict], dict[int, list(dict)]]:
        """
        Organizes chat data into structured information about participants and chats.
        Returns a tuple containing dictionaries of participants info and chat info.
        """
        participants_info = {}
        chats_info = {}
        for chat in queryset:
            participant = self.get_other_participant(chat)
            if not participant:
                continue

            self.update_participants_info(participants_info, participant, chat)
            self.append_chat_info(chats_info, participant, chat)

        return participants_info, chats_info

    def get_other_participant(self, chat: Chat) -> User:
        """
        Retrieves the chat participant other than the current user.
        """
        return chat.participants.exclude(id=self.request.user.id).first()

    def update_participants_info(self, participants_info: dict[int, dict], participant: User, chat: Chat):
        if participant.id not in participants_info:
            participants_info[participant.id] = {
                "user_id": participant.id,
                "user_name": participant.full_name,
                "user_role": participant.user_type,
                "profile_pic": participant.profile_pic.url if participant.profile_pic else None,
                "unread_messages_for_all_chats": self.get_unread_messages(chat),
            }
        else:
            participants_info[participant.id]["unread_messages_for_all_chats"] += self.get_unread_messages(chat)

    def append_chat_info(self, chats_info: dict[int, list(dict)], participant: User, chat: Chat):
        profile_name = chat.profile.full_name if chat.profile else participant.full_name
        role = participant.user_type
        if chat.profile and chat.profile.type and chat.profile.type == ProfileTypes.FIRST_TYPE:
            role = ProfileTypes.FIRST_TYPE
        if participant.id not in chats_info:
            chats_info[participant.id] = []

        chats_info[participant.id].append({
            "chat_id": chat.id,
            "room_id": str(chat.room_id),
            "profile_name": profile_name,
            "role": role,
            "profile_pic": chat.profile.profile_pic.url if chat.profile and chat.profile.profile_pic else None,
            "unread_messages": self.get_unread_messages(chat),
            "last_message": {
                "text": chat.messages.last().text,
                "author": chat.messages.last().author.id,
            } if chat.messages.exists() else None,
        })

    def get_unread_messages(self, chat: Chat) -> int:
        """
        Calculates the number of unread messages in a chat for the current user.
        """
        return chat.messages.filter(viewed=False).exclude(author=self.request.user).count()

    @staticmethod
    def prepare_response(participants_info: dict[int, dict], chats_info: dict[int, list(dict)]) -> list(dict):
        return [
            {"participant": participants_info[participant_id], "chats": chats}
            for participant_id, chats in chats_info.items()
        ]


class ArchivedChatListView(generics.ListAPIView):
    permission_classes: tuple = (CustomPermission2,)

    def get_queryset(self) -> QuerySet[Chat]:
        return Chat.objects.filter(is_deleted=True, participants=self.request.user)


class MessagePagination(PageNumberPagination):
    page_size: int = settings.CHAT_MESSAGES_PER_PAGE
    page_size_query_param: str = "page_size"
    max_page_size: int = settings.CHAT_MAX_MESSAGES_PER_PAGE


class ChatDetailView(generics.RetrieveAPIView):
    queryset: QuerySet = Chat.objects.filter(is_deleted=False)
    permission_classes: tuple = (CustomPermission2,)
    pagination_class = MessagePagination

    def get_queryset(self) -> QuerySet:
        # Handling for Swagger to avoid errors during schema generation
        if getattr(self, "swagger_fake_view", False):
            return Chat.objects.none()
        return Chat.objects.filter(participants=self.request.user)

    def get_serializer_context(self) -> dict[str, any]:
        context: dict[str, any] = super().get_serializer_context()
        context["request"] = self.request
        return context


class ChatContactView(generics.RetrieveAPIView):
    queryset: QuerySet[Chat] = Chat.objects.filter(is_deleted=False)
    serializer_class = ContactUserSerializer
    permission_classes: tuple = (CustomPermission2,)
    lookup_url_kwarg: str = "chat_id"

    def get(self, request: HttpRequest, *args, **kwargs) -> Response:
        current_user = request.user
        chat: Chat = self.get_object()
        contact_user = chat.participants.exclude(pk=current_user.pk).first()
        return Response(self.get_serializer(instance=contact_user).data)


class MarkMessagesAsViewedView(generics.UpdateAPIView):
    queryset: QuerySet[Chat] = Chat.objects.filter(is_deleted=False)
    serializer_class = MarkMessagesAsViewedSerializer
    permission_classes: tuple = (CustomPermission2,)

    def patch(self, request: HttpRequest, *args, **kwargs) -> Response:
        chat: Chat = self.get_object()
        messages = chat.messages.filter(viewed=False).exclude(author=request.user)
        messages.update(viewed=True)
        return Response({"message": "Messages marked as viewed"}, status=status.HTTP_200_OK)


class ChatCreateView(generics.CreateAPIView):
    queryset: QuerySet[Chat] = Chat.objects.filter(is_deleted=False)
    permission_classes: tuple = (CustomPermission3 | CustomPermission1 | IsAdminUser | CustomPermission4,)

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> JsonResponse:
        data: dict[str, Any] = json.loads(request.body)
        sender = request.user
        receiver = get_object_or_404(settings.AUTH_USER_MODEL, email=data["contact"])
        chat = Chat.create(sender, receiver)

        return JsonResponse({
            "id": chat.id,
            "room_id": str(chat.room_id),
            "participants": list(chat.participants.values_list("id", flat=True))
        }, status=status.HTTP_201_CREATED)


class ChatDeleteView(generics.DestroyAPIView):
    queryset: QuerySet[Chat] = Chat.objects.filter(is_deleted=False)
    serializer_class = ChatDeleteSerializer
    permission_classes: tuple = (CustomPermission3 | CustomPermission1 | IsAdminUser | CustomPermission4,)

    def delete(self, request: HttpRequest, *args: Any, **kwargs: Any) -> Response:
        chat = get_object_or_404(self.queryset, id=self.kwargs.get("pk"))
        chat.is_deleted = True
        chat.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ChatAttachmentListView(generics.ListAPIView):
    serializer_class: QuerySet[Chat] = ChatAttachmentSerializer
    permission_classes: tuple = (CustomPermission2,)
    parser_classes: tuple = (parsers.MultiPartParser,)

    def get_queryset(self) -> QuerySet:
        chat_id: str = self.kwargs.get("pk", "")
        return Attachment.objects.filter(message__chat_id=chat_id)
