import uuid
from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.db import models
from numuw.storage_backends import PrivateMediaStorage

from chat.utils import get_path, validate_file_extension

if TYPE_CHECKING:
    from profiles.models import Profile


class Chat(models.Model):
    participants = models.ManyToManyField(
        to=settings.AUTH_USER_MODEL, related_name="chats"
    )
    profile = models.ForeignKey(
        to="profiles.Profile", related_name="chats",
        on_delete=models.CASCADE, null=True, blank=True
    )
    is_deleted = models.BooleanField(default=False)
    room_id = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Chat {self.room_id}"

    @classmethod
    def create(cls,
               participant1: settings.AUTH_USER_MODEL,
               participant2: settings.AUTH_USER_MODEL,
               profile: Optional["Profile"] = None
               ) -> "Chat":
        if profile:
            chat = cls.objects.filter(profile=profile, participants=participant1).filter(participants=participant2)
        else:
            chat = cls.objects.filter(profile__isnull=True, participants=participant1).filter(participants=participant2)

        if chat.exists():
            return chat.first()

        chat = cls.objects.create(profile=profile)
        chat.participants.add(participant1, participant2)
        return chat


class Message(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="messages", on_delete=models.CASCADE)
    chat = models.ForeignKey(Chat, related_name="messages", on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    viewed = models.BooleanField(default=False)

    def __str__(self) -> str:
        return self.text


class Attachment(models.Model):
    message = models.OneToOneField(Message, related_name="chat_attachment", on_delete=models.CASCADE)
    filename = models.CharField(blank=False, max_length=255)
    file = models.FileField(upload_to=get_path, validators=[validate_file_extension], storage=PrivateMediaStorage())
    extension = models.CharField(max_length=10, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.filename
