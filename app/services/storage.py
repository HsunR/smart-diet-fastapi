import json
from io import BytesIO
from urllib.parse import quote

from minio import Minio

from app.core.config import settings


class ObjectStorage:
    """MinIO-backed object storage for user-uploaded files."""

    def __init__(self) -> None:
        self.bucket = settings.minio_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
        self.client.set_bucket_policy(self.bucket, self._public_read_policy())

    def upload_bytes(self, object_name: str, content: bytes, content_type: str | None = None) -> str:
        self.client.put_object(
            self.bucket,
            object_name,
            BytesIO(content),
            length=len(content),
            content_type=content_type or "application/octet-stream",
        )
        return self.public_url(object_name)

    def public_url(self, object_name: str) -> str:
        return f"{settings.minio_public_url.rstrip('/')}/{self.bucket}/{quote(object_name)}"

    def _public_read_policy(self) -> str:
        return json.dumps({
            "Version": "2012-10-17",
            "Statement": [{
                "Effect": "Allow",
                "Principal": {"AWS": ["*"]},
                "Action": ["s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{self.bucket}/*"],
            }],
        })


_storage: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    global _storage
    if _storage is None:
        _storage = ObjectStorage()
    return _storage
