import datetime

from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import serializers

from chat.models import Attachment, Chat, Message

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model: type[User] = User
        fields: tuple = ("full_name", "profile_pic")


class ContactUserSerializer(serializers.ModelSerializer):
    online = serializers.SerializerMethodField()
    local_time = serializers.SerializerMethodField()

    @staticmethod
    def get_online(obj: User) -> bool:
        if obj.last_active:
            now = timezone.now()
            return now - obj.last_active < datetime.timedelta(minutes=settings.USER_ONLINE_TIMEOUT_MINUTES)
        return False

    @staticmethod
    def get_local_time(obj: User) -> datetime.datetime:
        # TODO: Implement timezone conversion after adding this field to the User model
        return datetime.datetime.now()

    class Meta:
        model: type[User] = User
        fields: tuple = ("full_name", "profile_pic", "user_type", "online", "local_time")


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model: type[Message] = Message
        fields: tuple = ("author", "text", "created_at", "viewed")


class ChatDeleteSerializer(serializers.ModelSerializer):
    class Meta:
        model: type[Chat] = Chat
        fields: tuple = ("is_deleted",)


class ChatAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model: type[Attachment] = Attachment
        fields: tuple = ("id", "file", "extension")


class MarkMessagesAsViewedSerializer(serializers.ModelSerializer):
    class Meta:
        model: type[Message] = Message
        fields: tuple = ("id",)
        read_only_fields: tuple = ("id",)
