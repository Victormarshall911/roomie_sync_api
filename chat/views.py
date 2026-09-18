from rest_framework import permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.pagination import CursorPagination
from django.db.models import Q
from .models import Conversation, Message
from .serializers import (
    ConversationListSerializer,
    StartConversationSerializer,
    MessageSerializer,
)


class MessageCursorPagination(CursorPagination):
    page_size = 30
    ordering = 'created_at'


class ConversationListCreateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def get(self, request):
        user = request.user
        qs = Conversation.objects.filter(Q(user1=user) | Q(user2=user)).prefetch_related('messages', 'user1__profile', 'user2__profile')

        # Filter out blocked users
        try:
            from moderation.models import Block
            blocked_ids = Block.objects.filter(blocker=user).values_list('blocked_id', flat=True)
            blocking_ids = Block.objects.filter(blocked=user).values_list('blocker_id', flat=True)
            all_blocked = set(blocked_ids).union(set(blocking_ids))
            if all_blocked:
                qs = qs.exclude(user1_id__in=all_blocked).exclude(user2_id__in=all_blocked)
        except Exception:
            pass

        serializer = ConversationListSerializer(qs, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = StartConversationSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            conversation = serializer.save()
            data = ConversationListSerializer(conversation, context={'request': request}).data
            return Response(data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class MessageListCreateView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def _get_conversation(self, request, conversation_id):
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return None, Response({'detail': 'Conversation not found.'}, status=status.HTTP_404_NOT_FOUND)

        if request.user.id not in (conversation.user1_id, conversation.user2_id):
            return None, Response({'detail': 'You are not a participant in this conversation.'}, status=status.HTTP_403_FORBIDDEN)

        return conversation, None

    def get(self, request, conversation_id):
        conversation, error_response = self._get_conversation(request, conversation_id)
        if error_response:
            return error_response

        messages = conversation.messages.select_related('sender__profile').order_by('created_at')
        paginator = MessageCursorPagination()
        page = paginator.paginate_queryset(messages, request)
        serializer = MessageSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, conversation_id):
        conversation, error_response = self._get_conversation(request, conversation_id)
        if error_response:
            return error_response

        content = request.data.get('content', '').strip()
        if not content:
            return Response({'content': 'Message content cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)

        message = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            content=content
        )
        serializer = MessageSerializer(message)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class MarkConversationReadView(APIView):
    permission_classes = (permissions.IsAuthenticated,)

    def post(self, request, conversation_id):
        try:
            conversation = Conversation.objects.get(id=conversation_id)
        except Conversation.DoesNotExist:
            return Response({'detail': 'Conversation not found.'}, status=status.HTTP_404_NOT_FOUND)

        if request.user.id not in (conversation.user1_id, conversation.user2_id):
            return Response({'detail': 'You are not a participant in this conversation.'}, status=status.HTTP_403_FORBIDDEN)

        updated_count = conversation.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)
        return Response({'marked_read': updated_count}, status=status.HTTP_200_OK)
