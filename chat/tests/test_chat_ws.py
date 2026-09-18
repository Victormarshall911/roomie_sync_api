import pytest
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import AccessToken
from accounts.models import User
from profiles.models import Profile
from chat.models import Conversation, Message
from roomiesync.asgi import application


@pytest.fixture
def ws_alice(db):
    user = User.objects.create_user(email='ws_alice@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Alice WS'})
    user.profile = p
    return user


@pytest.fixture
def ws_bob(db):
    user = User.objects.create_user(email='ws_bob@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Bob WS'})
    user.profile = p
    return user


@pytest.fixture
def ws_charlie(db):
    user = User.objects.create_user(email='ws_charlie@unilag.edu.ng', password='Password123!', is_email_verified=True)
    p, _ = Profile.objects.update_or_create(user=user, defaults={'full_name': 'Charlie WS'})
    user.profile = p
    return user


@pytest.fixture
def ws_convo(db, ws_alice, ws_bob):
    u1, u2 = (ws_alice, ws_bob) if str(ws_alice.id) < str(ws_bob.id) else (ws_bob, ws_alice)
    return Conversation.objects.create(user1=u1, user2=u2)


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestChatWebSockets:
    async def test_two_users_connect_and_exchange_messages(self, ws_alice, ws_bob, ws_convo):
        token_alice = str(AccessToken.for_user(ws_alice))
        token_bob = str(AccessToken.for_user(ws_bob))

        # 1. Connect Alice
        comm_alice = WebsocketCommunicator(
            application,
            f"/ws/chat/{ws_convo.id}/?token={token_alice}"
        )
        connected_alice, _ = await comm_alice.connect()
        assert connected_alice is True

        # 2. Connect Bob
        comm_bob = WebsocketCommunicator(
            application,
            f"/ws/chat/{ws_convo.id}/?token={token_bob}"
        )
        connected_bob, _ = await comm_bob.connect()
        assert connected_bob is True

        # 3. Alice sends message
        await comm_alice.send_json_to({'content': 'Hello from Alice in Realtime!'})

        # 4. Both Alice and Bob receive the chat_message event
        response_bob = await comm_bob.receive_json_from(timeout=5)
        assert response_bob['type'] == 'new_message'
        assert response_bob['message']['content'] == 'Hello from Alice in Realtime!'
        assert response_bob['message']['sender_id'] == str(ws_alice.id)

        response_alice = await comm_alice.receive_json_from(timeout=5)
        assert response_alice['type'] == 'new_message'
        assert response_alice['message']['content'] == 'Hello from Alice in Realtime!'

        # 5. Bob also receives unread_badge_update on his personal user group
        badge_update = await comm_bob.receive_json_from(timeout=5)
        assert badge_update['type'] == 'unread_badge_update'
        assert badge_update['data']['conversation_id'] == str(ws_convo.id)

        # 6. Disconnect both cleanly
        await comm_alice.disconnect()
        await comm_bob.disconnect()

    async def test_third_party_rejected_from_conversation(self, ws_charlie, ws_convo):
        token_charlie = str(AccessToken.for_user(ws_charlie))

        comm_charlie = WebsocketCommunicator(
            application,
            f"/ws/chat/{ws_convo.id}/?token={token_charlie}"
        )
        connected, close_code = await comm_charlie.connect()
        assert connected is False
        assert close_code == 4003

    async def test_unauthenticated_connection_rejected(self, ws_convo):
        comm_anon = WebsocketCommunicator(
            application,
            f"/ws/chat/{ws_convo.id}/"
        )
        connected, close_code = await comm_anon.connect()
        assert connected is False
        assert close_code == 4001
