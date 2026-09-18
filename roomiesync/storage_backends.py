import os
from django.conf import settings
from django.core.files.storage import FileSystemStorage

try:
    from storages.backends.s3boto3 import S3Boto3Storage
    HAS_S3_STORAGES = True
except ImportError:
    HAS_S3_STORAGES = False
    S3Boto3Storage = FileSystemStorage


class PublicMediaStorage(S3Boto3Storage if HAS_S3_STORAGES else FileSystemStorage):
    """
    Storage backend for public assets (avatars, listing images).
    Accessible via public CDN / R2 public URL / S3 bucket without signed query parameters.
    """
    file_overwrite = False
    default_acl = None
    querystring_auth = False

    def __init__(self, *args, **kwargs):
        if not (getattr(settings, 'AWS_ACCESS_KEY_ID', None) and getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)):
            super(FileSystemStorage, self).__init__(*args, **kwargs)
            return

        # Cloudflare R2 or custom domain handling
        custom_domain = getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', None)
        if custom_domain:
            kwargs['custom_domain'] = custom_domain

        endpoint_url = getattr(settings, 'AWS_S3_ENDPOINT_URL', None)
        if endpoint_url:
            kwargs['endpoint_url'] = endpoint_url

        super().__init__(*args, **kwargs)


class PrivateMediaStorage(S3Boto3Storage if HAS_S3_STORAGES else FileSystemStorage):
    """
    Storage backend for sensitive documents (student verification IDs).
    Private access strictly enforced; generates time-limited presigned URLs (1800s / 30m).
    """
    file_overwrite = False
    default_acl = None
    custom_domain = None
    querystring_auth = True
    querystring_expire = 1800  # 30 minutes

    def __init__(self, *args, **kwargs):
        if not (getattr(settings, 'AWS_ACCESS_KEY_ID', None) and getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)):
            super(FileSystemStorage, self).__init__(*args, **kwargs)
            return

        endpoint_url = getattr(settings, 'AWS_S3_ENDPOINT_URL', None)
        if endpoint_url:
            kwargs['endpoint_url'] = endpoint_url

        super().__init__(*args, **kwargs)
