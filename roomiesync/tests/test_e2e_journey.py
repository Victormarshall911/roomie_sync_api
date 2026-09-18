import uuid
from unittest.mock import patch, MagicMock
import pytest
from asgiref.sync import async_to_sync
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from channels.testing import WebsocketCommunicator
from rest_framework_simplejwt.tokens import RefreshToken
from roomiesync.asgi import application
from accounts.models import User
from accounts.otp import get_otp
from profiles.models import Profile
from listings.models import Listing, ListingImage
from moderation.models import Block, Report
from verification.models import VerificationRequest
from notifications.models import DeviceToken


def create_dummy_image(name='test.png'):
    return SimpleUploadedFile(
        name=name,
        content=b'GIF89a\x01\x00\x01\x00\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;',
        content_type='image/png'
    )


@pytest.mark.django_db(transaction=True)
class TestFullRoomieSyncUserJourney:
    def test_end_to_end_user_journey(self):
        """
        Complete end-to-end user lifecycle test:
        1. Registration with onboarding staged payload (User + Profile).
        2. OTP verification via Redis cache.
        3. Profile completion & avatar upload.
        4. Student ID document upload.
        5. Admin approval of student verification.
        6. Listing creation with multi-image ordering.
        7. Roommate matching calculation.
        8. Real-time WebSocket chat communication & read receipts.
        9. Push notification dispatch for new messages.
        10. Moderation (report & block) and exclusion filtering.
        11. Account deletion.
        """
        client = APIClient()

        # -------------------------------------------------------------
        # 1. Registration with onboarding staged payload (Student A)
        # -------------------------------------------------------------
        student_a_email = 'student_a@university.edu'
        reg_payload_a = {
            'email': student_a_email,
            'password': 'SecurePassword123!',
            'profile': {
                'full_name': 'Alice Student',
                'university': 'State University',
                'budget_min': 50000,
                'budget_max': 100000,
                'sleep_habit': 'Night Owl',
                'cleanliness': 8,
                'socializing': 'Rarely',
                'smoking': 'No',
                'noise_level': 'Quiet',
                'study_time': 'Night',
                'drinking_habit': 'Socially',
                'pets_preference': 'Love them',
                'location_preference': 'Campus Gate',
                'searching_for': 'Listing a Space',
            }
        }

        res_reg_a = client.post('/api/v1/auth/register/', reg_payload_a, format='json')
        assert res_reg_a.status_code == 201
        assert res_reg_a.data['user']['email'] == student_a_email
        assert res_reg_a.data['user']['is_email_verified'] is False
        token_a = res_reg_a.data['tokens']['access']

        user_a = User.objects.get(email=student_a_email)
        profile_a = Profile.objects.get(user=user_a)
        assert profile_a.full_name == 'Alice Student'
        assert profile_a.cleanliness == 8
        assert profile_a.is_verified is False

        # -------------------------------------------------------------
        # 2. Email verification using Redis OTP
        # -------------------------------------------------------------
        otp_code = get_otp(student_a_email)
        assert otp_code is not None

        res_verify_a = client.post('/api/v1/auth/verify-email/', {
            'email': student_a_email,
            'code': otp_code
        }, format='json')
        assert res_verify_a.status_code == 200
        user_a.refresh_from_db()
        assert user_a.is_email_verified is True

        # -------------------------------------------------------------
        # 3. Avatar upload & Profile update
        # -------------------------------------------------------------
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_a}")
        avatar_img = create_dummy_image('alice.png')
        res_profile_update = client.patch(
            '/api/v1/profiles/me/',
            {'avatar': avatar_img, 'department': 'Computer Science'},
            format='multipart'
        )
        assert res_profile_update.status_code == 200
        profile_a.refresh_from_db()
        assert profile_a.department == 'Computer Science'
        assert profile_a.avatar.name is not None

        # -------------------------------------------------------------
        # 4. Student Verification Document Submission
        # -------------------------------------------------------------
        student_id_doc = SimpleUploadedFile('admission_letter.pdf', b'%PDF-1.4 sample', content_type='application/pdf')
        res_verif_sub = client.post(
            '/api/v1/verification/submit/',
            {'document': student_id_doc},
            format='multipart'
        )
        assert res_verif_sub.status_code == 201
        assert res_verif_sub.data['status'] == 'pending'

        # Duplicate pending submission is prevented
        res_dup_sub = client.post(
            '/api/v1/verification/submit/',
            {'document': student_id_doc},
            format='multipart'
        )
        assert res_dup_sub.status_code == 400

        # -------------------------------------------------------------
        # 5. Admin Review: Generate signed URL & Approve
        # -------------------------------------------------------------
        admin_user = User.objects.create_superuser(
            email='admin@university.edu',
            password='AdminPassword123!'
        )
        Profile.objects.filter(user=admin_user).update(is_admin=True)
        admin_refresh = RefreshToken.for_user(admin_user)
        admin_token = str(admin_refresh.access_token)

        admin_client = APIClient()
        admin_client.credentials(HTTP_AUTHORIZATION=f"Bearer {admin_token}")

        # List pending verifications
        res_admin_list = admin_client.get('/api/v1/admin/verifications/')
        assert res_admin_list.status_code == 200
        assert len(res_admin_list.data['results']) == 1
        assert res_admin_list.data['results'][0]['user_email'] == student_a_email

        # Request signed URL for document
        res_admin_doc_url = admin_client.get(f"/api/v1/admin/verifications/{user_a.id}/document/")
        assert res_admin_doc_url.status_code == 200
        assert res_admin_doc_url.data['expires_in'] == 1800  # 30-min guaranteed expiry
        signed_download_url = res_admin_doc_url.data['document_url']

        # Download via signed URL (unauthenticated)
        unauth_client = APIClient()
        res_doc_dl = unauth_client.get(signed_download_url)
        assert res_doc_dl.status_code == 200

        # Admin approves verification
        res_approve = admin_client.post(f"/api/v1/admin/verifications/{user_a.id}/approve/")
        assert res_approve.status_code == 200
        assert res_approve.data['is_verified'] is True

        profile_a.refresh_from_db()
        assert profile_a.is_verified is True

        # -------------------------------------------------------------
        # 6. Listing Creation with Multi-image ordering
        # -------------------------------------------------------------
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_a}")
        img1 = create_dummy_image('room1.png')
        img2 = create_dummy_image('room2.png')

        listing_payload = {
            'title': 'Spacious 2-Bedroom Near Campus Gate',
            'description': 'Walking distance to engineering faculty. Clean and furnished.',
            'price': 85000,
            'location': 'Campus Gate',
            'type': 'Room',
            'searching_for': 'Listing a Space',
            'uploaded_images': [img1, img2]
        }
        res_listing_create = client.post('/api/v1/listings/', listing_payload, format='multipart')
        assert res_listing_create.status_code == 201
        listing_id = res_listing_create.data['id']
        assert len(res_listing_create.data['images']) == 2
        assert res_listing_create.data['is_available'] is True

        # Toggle availability
        res_toggle = client.post(f"/api/v1/listings/{listing_id}/toggle-availability/")
        assert res_toggle.status_code == 200
        assert res_toggle.data['is_available'] is False

        # Toggle back to available
        res_toggle_back = client.post(f"/api/v1/listings/{listing_id}/toggle-availability/")
        assert res_toggle_back.status_code == 200
        assert res_toggle_back.data['is_available'] is True

        # -------------------------------------------------------------
        # 7. Student B Registration & Roommate Matching
        # -------------------------------------------------------------
        student_b_email = 'student_b@university.edu'
        reg_payload_b = {
            'email': student_b_email,
            'password': 'SecurePassword456!',
            'profile': {
                'full_name': 'Bob Student',
                'university': 'State University',
                'budget_min': 60000,
                'budget_max': 95000,
                'sleep_habit': 'Night Owl',
                'cleanliness': 8,
                'socializing': 'Rarely',
                'smoking': 'No',
                'noise_level': 'Quiet',
                'study_time': 'Night',
                'drinking_habit': 'Socially',
                'pets_preference': 'Love them',
                'location_preference': 'Campus Gate',
                'searching_for': 'Looking for Roommate',
            }
        }
        res_reg_b = client.post('/api/v1/auth/register/', reg_payload_b, format='json')
        assert res_reg_b.status_code == 201
        token_b = res_reg_b.data['tokens']['access']
        user_b = User.objects.get(email=student_b_email)

        # Verify Student B email
        otp_b = get_otp(student_b_email)
        client.post('/api/v1/auth/verify-email/', {'email': student_b_email, 'code': otp_b}, format='json')

        # Student B checks matches
        client_b = APIClient()
        client_b.credentials(HTTP_AUTHORIZATION=f"Bearer {token_b}")

        res_matches = client_b.get('/api/v1/matches/')
        assert res_matches.status_code == 200
        assert len(res_matches.data) >= 1
        match_a = next(m for m in res_matches.data if m['id'] == str(user_a.id))
        # High compatibility expected due to identical lifestyle answers
        assert match_a['match_percentage'] >= 80

        # Student B browses listings
        res_feed = client_b.get('/api/v1/listings/?location=Campus Gate')
        assert res_feed.status_code == 200
        assert any(item['id'] == listing_id for item in res_feed.data['results'])

        # -------------------------------------------------------------
        # 8. Start Conversation & Real-time WebSocket messaging
        # -------------------------------------------------------------
        # Register Student A device push token
        DeviceToken.objects.create(
            user=user_a,
            token='ExponentPushToken[student_a_device_12345]'
        )

        res_conv = client_b.post('/api/v1/chat/conversations/', {
            'recipient_id': str(user_a.id)
        }, format='json')
        assert res_conv.status_code in (200, 201)
        conversation_id = res_conv.data['id']

        # WebSocket real-time communication via async_to_sync with mocked Expo push service
        mock_expo_resp = MagicMock()
        mock_expo_resp.json.return_value = {'data': [{'status': 'ok'}]}

        with patch('requests.post', return_value=mock_expo_resp) as mock_expo_post:
            async def run_websocket_chat():
                ws_url_b = f"/ws/chat/{conversation_id}/?token={token_b}"
                communicator_b = WebsocketCommunicator(application, ws_url_b)
                connected_b, _ = await communicator_b.connect()
                assert connected_b is True

                ws_url_a = f"/ws/chat/{conversation_id}/?token={token_a}"
                communicator_a = WebsocketCommunicator(application, ws_url_a)
                connected_a, _ = await communicator_a.connect()
                assert connected_a is True

                # Send message from Student B
                await communicator_b.send_json_to({
                    'content': 'Hi Alice! I saw your room listing near Campus Gate.'
                })

                # Receive real-time message on Student A's WebSocket
                response_a = await communicator_a.receive_json_from(timeout=5)
                assert response_a['type'] == 'new_message'
                assert response_a['message']['content'] == 'Hi Alice! I saw your room listing near Campus Gate.'
                assert response_a['message']['sender_id'] == str(user_b.id)
                assert response_a['message']['is_read'] is False

                # Receive unread badge notification on Student A's personal group
                badge_a = await communicator_a.receive_json_from(timeout=5)
                assert badge_a['type'] == 'unread_badge_update'
                assert badge_a['data']['conversation_id'] == str(conversation_id)

                await communicator_a.disconnect()
                await communicator_b.disconnect()

            async_to_sync(run_websocket_chat)()

            # Assert push notification was dispatched with exact payload structure
            assert mock_expo_post.called
            push_payload = mock_expo_post.call_args[1]['json']
            assert len(push_payload) == 1
            assert push_payload[0]['to'] == 'ExponentPushToken[student_a_device_12345]'
            assert 'Alice' in push_payload[0]['title'] or 'Bob' in push_payload[0]['title']
            assert push_payload[0]['data']['type'] == 'chat'
            assert push_payload[0]['data']['conversationId'] == str(conversation_id)

        # Student A marks conversation as read via REST
        client_a = APIClient()
        client_a.credentials(HTTP_AUTHORIZATION=f"Bearer {token_a}")
        res_read = client_a.post(f"/api/v1/chat/conversations/{conversation_id}/read/")
        assert res_read.status_code == 200
        assert res_read.data['marked_read_count'] >= 1

        # -------------------------------------------------------------
        # 9. Moderation: Report and Block
        # -------------------------------------------------------------
        # Student A reports Student B
        res_report = client_a.post('/api/v1/moderation/reports/', {
            'reported_user_id': str(user_b.id),
            'reason': 'inappropriate_behavior'
        }, format='json')
        assert res_report.status_code == 201
        assert Report.objects.filter(reporter=user_a, reported_user=user_b).exists()

        # Student A blocks Student B
        res_block = client_a.post('/api/v1/moderation/blocks/', {
            'blocked_id': str(user_b.id)
        }, format='json')
        assert res_block.status_code == 201
        assert Block.objects.filter(blocker=user_a, blocked=user_b).exists()

        # Verify Student B is excluded from Student A's conversations list
        res_inbox_a = client_a.get('/api/v1/chat/conversations/')
        assert res_inbox_a.status_code == 200
        assert not any(c['id'] == conversation_id for c in res_inbox_a.data['results'])

        # -------------------------------------------------------------
        # 10. Account Deletion (Self-serve GDPR/Security)
        # -------------------------------------------------------------
        res_delete_b = client_b.delete('/api/v1/auth/me/')
        assert res_delete_b.status_code == 204
        assert not User.objects.filter(id=user_b.id).exists()
