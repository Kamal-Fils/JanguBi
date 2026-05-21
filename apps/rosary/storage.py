from django.conf import settings
from storages.backends.s3boto3 import S3Boto3Storage
from urllib.parse import urlparse

class RosaryAudioStorage(S3Boto3Storage):
    """
    Custom storage backend mapping strictly to the `rosary-audio` S3 bucket.
    """
    bucket_name = "rosary-audio"
    file_overwrite = False
    default_acl = "private"
    
    # Force settings that bypass AWS defaults so we route to local MinIO
    access_key = getattr(settings, 'AWS_S3_ACCESS_KEY_ID', None)
    secret_key = getattr(settings, 'AWS_S3_SECRET_ACCESS_KEY', None)
    endpoint_url = getattr(settings, 'AWS_S3_ENDPOINT_URL', None)
    region_name = getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')
    signature_version = getattr(settings, 'AWS_S3_SIGNATURE_VERSION', 's3v4')
    addressing_style = "path"

    def __init__(self, *args, **kwargs):
        # Disable pre-signed URLs since the bucket is public
        kwargs['querystring_auth'] = False

        # Prefer explicit public domain; fallback to endpoint host without hardcoding localhost.
        custom_domain = (getattr(settings, 'AWS_S3_CUSTOM_DOMAIN', '') or '').strip()
        if custom_domain:
            kwargs['custom_domain'] = custom_domain
        else:
            # Prefer public-facing URL over internal Docker service name
            public_url = getattr(settings, 'MINIO_PUBLIC_URL', None) or getattr(settings, 'AWS_S3_ENDPOINT_URL', None)
            if public_url:
                parsed = urlparse(public_url)
                if parsed.netloc:
                    kwargs['custom_domain'] = f"{parsed.netloc}/{self.bucket_name}"
            
        super().__init__(*args, **kwargs)

        if not getattr(settings, 'AWS_S3_USE_SSL', False):
            self.url_protocol = "http:"

