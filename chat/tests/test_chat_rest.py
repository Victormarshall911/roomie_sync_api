import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from accounts.models import User
from profiles.models import Profile
from moderation.models import Block
from chat.models import Conversation, Message


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def alice(db):
    user = User.objects.create_user(email='alice@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Alice User'})
    user.profile = p
    return user


@pytest.fixture
def bob(db):
    user = User.objects.create_user(email='bob@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Bob User'})
    user.profile = p
    return user


@pytest.fixture
def charlie(db):
    user = User.objects.create_user(email='charlie@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Charlie User'})
    user.profile = p
    return user


@pytest.mark.django_db
class TestChatREST:
    def test_canonical_ordering_and_duplicate_prevention(self, api_client, alice, bob):
        url = reverse('conversation-list-create')

        # Alice starts conversation with Bob
        api_client.force_authenticate(user=alice)
        res1 = api_client.post(url, {'recipient_id': str(bob.id)}, format='json')
        assert res1.status_code == status.HTTP_200_OK
        conv_id_1 = res1.data['id']

        # Bob starts conversation with Alice (reversed order)
        api_client.force_authenticate(user=bob)
        res2 = api_client.post(url, {'recipient_id': str(alice.id)}, format='json')
        assert res2.status_code == status.HTTP_200_OK
        conv_id_2 = res2.data['id']

        # Must return the SAME conversation ID
        assert conv_id_1 == conv_id_2
        assert Conversation.objects.count() == 1

        # Check model-level canonical ordering
        convo = Conversation.objects.first()
        min_u, max_u = (alice, bob) if str(alice.id) < str(bob.id) else (bob, alice)
        assert convo.user1_id == min_u.id
        assert convo.user2_id == max_u.id

    def test_message_history_ordering_and_pagination(self, api_client, alice, bob):
        u1, u2 = (alice, bob) if str(alice.id) < str(bob.id) else (bob, alice)
        convo = Conversation.objects.create(user1=u1, user2=u2)

        # Create 35 messages
        for i in range(35):
            Message.objects.create(
                conversation=convo,
                sender=alice if i % 2 == 0 else bob,
                content=f"Message {i}"
            )

        api_client.force_authenticate(user=alice)
        url = reverse('message-list-create', kwargs={'conversation_id': convo.id})
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data['results']) == 30
        assert response.data['next'] is not None
        assert response.data['results'][0]['content'] == 'Message 0'

    def test_send_message_rest_fallback(self, api_client, alice, bob):
        u1, u2 = (alice, bob) if str(alice.id) < str(bob.id) else (bob, alice)
        convo = Conversation.objects.create(user1=u1, user2=u2)

        api_client.force_authenticate(user=alice)
        url = reverse('message-list-create', kwargs={'conversation_id': convo.id})
        res = api_client.post(url, {'content': 'Hello from Alice!'}, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data['content'] == 'Hello from Alice!'
        assert res.data['sender_id'] == str(alice.id)
        assert res.data['is_read'] is False

    def test_mark_as_read(self, api_client, alice, bob):
        u1, u2 = (alice, bob) if str(alice.id) < str(bob.id) else (bob, alice)
        convo = Conversation.objects.create(user1=u1, user2=u2)

        # Alice sends 2 messages to Bob
        Message.objects.create(conversation=convo, sender=alice, content="Hi 1", is_read=False)
        Message.objects.create(conversation=convo, sender=alice, content="Hi 2", is_read=False)

        # Bob checks inbox unread count
        api_client.force_authenticate(user=bob)
        inbox_url = reverse('conversation-list-create')
        inbox_res = api_client.get(inbox_url)
        assert inbox_res.data[0]['unread_count'] == 2

        # Bob marks conversation as read
        read_url = reverse('conversation-mark-read', kwargs={'conversation_id': convo.id})
        read_res = api_client.post(read_url)
        assert read_res.status_code == status.HTTP_200_OK
        assert read_res.data['marked_read'] == 2

        # Verify messages are now read
        assert Message.objects.filter(conversation=convo, is_read=False).count() == 0

    def test_non_participant_cannot_access_or_send_messages(self, api_client, alice, bob, charlie):
        u1, u2 = (alice, bob) if str(alice.id) < str(bob.id) else (bob, alice)
        convo = Conversation.objects.create(user1=u1, user2=u2)

        api_client.force_authenticate(user=charlie)
        url = reverse('message-list-create', kwargs={'conversation_id': convo.id})

        # Charlie tries to read Alice & Bob's messages -> 403
        res_read = api_client.get(url)
        assert res_read.status_code == status.HTTP_403_FORBIDDEN

        # Charlie tries to post message to Alice & Bob's conversation -> 403
        res_send = api_client.post(url, {'content': 'Sneaky message'}, format='json')
        assert res_send.status_code == status.HTTP_403_FORBIDDEN

    def test_blocked_users_excluded_from_conversation_list(self, api_client, alice, bob):
        u1, u2 = (alice, bob) if str(alice.id) < str(bob.id) else (bob, alice)
        convo = Conversation.objects.create(user1=u1, user2=u2)
        Message.objects.create(conversation=convo, sender=bob, content="Hello")

        inbox_url = reverse('conversation-list-create')

        # Alice can see the conversation initially
        api_client.force_authenticate(user=alice)
        res1 = api_client.get(inbox_url)
        assert len(res1.data) == 1

        # Alice blocks Bob
        Block.objects.create(blocker=alice, blocked=bob)

        # Alice's inbox should no longer show the conversation with Bob
        res2 = api_client.get(inbox_url)
        assert len(res2.data) == 0
