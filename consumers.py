import json
import logging
import math
import os
from typing import Any

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.paginator import Page, Paginator
from django.db import transaction
from rest_framework.authtoken.models import Token

from chat.models import Attachment, Chat, Message
from chat.serializers import MessageSerializer

User = get_user_model()


class ChatConsumer(WebsocketConsumer):
    room_name: str
    room_group_name: str

    def connect(self):
        self.room_name: str = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group_name: str = f"chat_{self.room_name}"

        logging.info("Connecting to room group")
        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name, self.channel_name
        )

        self.accept()

    def disconnect(self, close_code: int):
        logging.warning(f"Disconnecting consumer with code {close_code}")
        async_to_sync(self.channel_layer.group_discard)(
            self.room_group_name, self.channel_name
        )

    def receive(self, text_data: str):
        logging.info("Receiving message from WebSocket")
        data: dict[str, Any] = json.loads(text_data)
        command: str = data.get("command", "")

        if command == "set_token":
            self.authenticate_user(token=data.get("token"))

        elif command in ["fetch_messages", "new_message", "share_file"]:
            if self.scope["user"].is_authenticated:
                self.handle_commands(command, data)
            else:
                self.close()

    def handle_commands(self, command: str, data: dict[str, Any]):
        if command == "fetch_messages":
            self.fetch_messages(data)
        elif command == "new_message":
            self.new_message(data)
        elif command == "share_file":
            self.share_file(data)
        else:
            self.send_message({"command": "error", "message": "Invalid command."})

    def authenticate_user(self, token: str):
        try:
            token_obj = Token.objects.get(key=token)
            self.scope["user"] = token_obj.user
        except Token.DoesNotExist:
            self.send_message({"command": "error", "message": "Invalid token."})
            self.close()

    def send_message(self, content: dict[str, Any]):
        self.send(text_data=json.dumps(content))

    def send_chat_message(self, message: dict[str, Any]):
        logging.info("Sending message to room group")
        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name, {"type": "chat_message", **message}
        )

    # Receive message from room group
    def chat_message(self, event):
        message = event["message"]
        self.send(text_data=json.dumps(message))

    @staticmethod
    def _get_paginated_data(chat: Chat, page_number: int, messages_per_page: int = 20) -> tuple[Page, int]:
        paginator: Paginator = Paginator(chat.messages.order_by("-created_at").all(), messages_per_page)
        messages: Page = paginator.get_page(page_number)
        max_pages: int = math.ceil(paginator.count / paginator.per_page)
        return messages, max_pages

    def messages_to_json(self, messages: list[Message]) -> list[dict[str, Any]]:
        return [self.message_to_json(message) for message in messages]

    @staticmethod
    def message_to_json(message: Message) -> dict[str, Any]:
        json_data: dict[str, Any] = {
            "id": message.id,
            "author": message.author.email,
            "content": message.text,
            "timestamp": str(message.created_at),
            "room_id": str(message.chat.room_id),
        }
        if hasattr(message, "chat_attachment"):
            json_data["attachment"] = {
                "filename": message.chat_attachment.filename,
                "size": message.chat_attachment.size,
                "url": message.chat_attachment.file.url,
                "extension": message.chat_attachment.extension,
            }
        return json_data

    def fetch_messages(self, data):
        room_id = data.get("room_id")
        page_number = int(data.get("page_number", 1))
        try:
            chat: Chat = Chat.objects.get(room_id=room_id)
            messages, max_pages = self._get_paginated_data(chat, page_number)
            content = {
                "command": "messages",
                "messages": self.messages_to_json(list(messages)),
                "max_pages": max_pages,
            }
            self.send_message(content)
        except Chat.DoesNotExist:
            error_message = {
                "command": "error",
                "message": "Chat room not found.",
            }
            self.send_message(error_message)

    def share_file(self, data):
        author_id: str = data.get("from")
        room_id: str = data.get("room_id")
        file_data: dict[str, Any] = data.get("file")
        filename: str = file_data.get("filename")
        filesize: int = file_data.get("size")
        file_content: str = file_data.get("data")  # Assuming base64 encoded string for simplicity

        try:
            author_user: User = User.objects.get(id=author_id)
            chat: Chat = Chat.objects.get(room_id=room_id)
            # Additional logic to handle file saving and message creation...
        except (User.DoesNotExist, Chat.DoesNotExist) as e:
            error_message = {
                "command": "error",
                "message": str(e),
            }
            self.send_message(error_message)
            return

        file_bytes = bytes(file_content)
        content_file = ContentFile(file_bytes)
        content_file.name = filename

        # Create a new Message instance for the file
        with transaction.atomic():
            message = Message.objects.create(
                author=author_user,
                chat=chat,
                text=f"File: {filename}"
            )
            message_attachment = Attachment.objects.create(
                message=message,
                filename=filename,
                size=filesize,
                extension=os.path.splitext(filename)[1][1:]
            )
            message_attachment.file.save(filename, content_file)

        serialized_data = MessageSerializer(message).data
        serializer = MessageSerializer(data=serialized_data)
        if serializer.is_valid():
            attachment = message.chat_attachment
            json_data = {
                "id": message.id,
                "author": message.author.email,
                "content": message.text,
                "timestamp": str(message.created_at),
                "room_id": str(message.chat.room_id),
                "attachment": {
                    "filename": attachment.filename,
                    "size": attachment.size,
                    "url": attachment.file.url,
                    "extension": attachment.extension,
                }
            }
            content = {
                "command": "new_message",
                "author": author_user,
                "message": json_data,
            }
            self.send_chat_message(content)

    def new_message(self, data: dict[str, Any]):
        author_id: str = data.get("from")
        room_id: str = data.get("room_id")
        message_text: str = data.get("message")

        try:
            author_user: User = User.objects.get(id=author_id)
            chat: Chat = Chat.objects.get(room_id=room_id)
            message: Message = Message.objects.create(
                author=author_user,
                chat=chat,
                text=message_text
            )
            content: dict[str, Any] = {
                "command": "new_message",
                "message": self.message_to_json(message)
            }
            self.send_chat_message(content)
        except User.DoesNotExist:
            error_message: dict[str, Any] = {
                "command": "error",
                "message": "Author not found.",
            }
            self.send_message(error_message)
            return
        except Chat.DoesNotExist:
            error_message: dict[str, Any] = {
                "command": "error",
                "message": "Chat room not found.",
            }
            self.send_message(error_message)
            return
