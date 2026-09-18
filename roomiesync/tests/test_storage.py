import pytest
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from accounts.models import User
from profiles.models import Profile
from listings.models import Listing, ListingImage
from verification.models import VerificationRequest
from admin_management.views import generate_signed_document_url, DOCUMENT_SIGNED_URL_EXPIRY_SECONDS


@pytest.mark.django_db
class TestStorageConfiguration:
    def test_default_storage_fallback(self):
        """Verify that missing AWS credentials correctly fall back to local FileSystemStorage."""
        storage_backend = settings.STORAGES['default']['BACKEND']
        assert 'FileSystemStorage' in storage_backend

    def test_signed_url_expiration_fixes_60s_bug(self):
        """Verify that document signed URL expiration is 1800s (30m) and strictly not the buggy 60s."""
        user = User.objects.create_user(email='test_storage_verif@university.edu', password='Password123!')
        verif = VerificationRequest.objects.create(
            user=user,
            document=SimpleUploadedFile('student_id.pdf', b'%PDF-1.4 test', content_type='application/pdf')
        )
        url, expires_in = generate_signed_document_url(verif)
        assert expires_in == 1800
        assert expires_in != 60
        assert DOCUMENT_SIGNED_URL_EXPIRY_SECONDS == 1800
        assert 'token=' in url

        # Clean up created file
        if verif.document:
            verif.document.delete(save=False)


@pytest.mark.django_db
class TestStorageCleanupSignals:
    def test_avatar_cleanup_on_change_and_delete(self):
        """
        Verify that replacing an avatar deletes the old avatar from storage,
        and deleting the profile deletes the active avatar.
        """
        user = User.objects.create_user(email='avatar_cleanup@university.edu', password='Password123!')
        profile, _ = Profile.objects.get_or_create(user=user)

        # Upload first avatar
        file1 = SimpleUploadedFile('avatar1.jpg', b'image-bytes-1', content_type='image/jpeg')
        profile.avatar = file1
        profile.save()

        path1 = profile.avatar.name
        assert default_storage.exists(path1)

        # Replace with second avatar
        file2 = SimpleUploadedFile('avatar2.jpg', b'image-bytes-2', content_type='image/jpeg')
        profile.avatar = file2
        profile.save()

        path2 = profile.avatar.name
        # path1 must be deleted, path2 must exist
        assert not default_storage.exists(path1)
        assert default_storage.exists(path2)

        # Delete profile
        profile.delete()
        assert not default_storage.exists(path2)

    def test_listing_image_cleanup_on_delete(self):
        """Verify that deleting a ListingImage deletes the image file from storage."""
        user = User.objects.create_user(email='listing_storage@university.edu', password='Password123!')
        listing = Listing.objects.create(
            user=user,
            title='Storage Test Listing',
            description='Testing image cleanup',
            price=80000,
            location='Campus North',
            type='Room',
            searching_for='Listing a Space'
        )

        img_file = SimpleUploadedFile('room.jpg', b'room-image-data', content_type='image/jpeg')
        listing_image = ListingImage.objects.create(listing=listing, image=img_file, order=0)
        img_path = listing_image.image.name
        assert default_storage.exists(img_path)

        # Delete listing image
        listing_image.delete()
        assert not default_storage.exists(img_path)

    def test_verification_document_cleanup_on_delete(self):
        """Verify that deleting a VerificationRequest deletes the document from storage."""
        user = User.objects.create_user(email='verif_storage@university.edu', password='Password123!')
        doc_file = SimpleUploadedFile('acceptance_letter.pdf', b'%PDF-content', content_type='application/pdf')
        verif = VerificationRequest.objects.create(user=user, document=doc_file)
        doc_path = verif.document.name
        assert default_storage.exists(doc_path)

        # Delete verification request
        verif.delete()
        assert not default_storage.exists(doc_path)
