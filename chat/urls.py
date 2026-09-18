from django.urls import path
from .views import (
    ConversationListCreateView,
    MessageListCreateView,
    MarkConversationReadView,
)

urlpatterns = [
    path('conversations/', ConversationListCreateView.as_view(), name='conversation-list-create'),
    path('conversations/<uuid:conversation_id>/messages/', MessageListCreateView.as_view(), name='message-list-create'),
    path('conversations/<uuid:conversation_id>/read/', MarkConversationReadView.as_view(), name='conversation-mark-read'),
]
