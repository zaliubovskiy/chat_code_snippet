from django.urls import path

from chat.views import (
    ArchivedChatListView,
    ChatAttachmentListView,
    ChatContactView,
    ChatCreateView,
    ChatDeleteView,
    ChatDetailView,
    ChatListView,
    MarkMessagesAsViewedView,
)

urlpatterns = [
    path("", ChatListView.as_view()),
    path("profiles/<int:pk>/", ChatListView.as_view()),
    path("<int:chat_id>/viewed/", MarkMessagesAsViewedView.as_view()),

    # TODO: implement next endpoints on frontend
    path("<int:chat_id>/contact/", ChatContactView.as_view()),
    path("<int:pk>/delete/", ChatDeleteView.as_view()),
    path("<int:pk>/", ChatDetailView.as_view()),
    path("create/", ChatCreateView.as_view()),
    path("archive/", ArchivedChatListView.as_view()),
    path("<int:pk>/attachments/", ChatAttachmentListView.as_view()),
]
