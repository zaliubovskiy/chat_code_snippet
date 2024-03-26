from django.contrib import admin

from chat.models import Chat


class ChatAdmin(admin.ModelAdmin):
    list_display = ("room_id", "participants", "profile", "is_deleted", "created_at",)


admin.site.register(Chat, ChatAdmin)

