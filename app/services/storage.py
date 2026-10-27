from datetime import timedelta
from io import BytesIO
from urllib.parse import quote, unquote, urlsplit

from minio import Minio
from minio.error import S3Error

from app.core.config import settings


class ObjectStorage:
    """私有 MinIO 对象；稳定引用入库，临时签名地址仅用于展示。"""

    def __init__(self) -> None:
        """根据应用配置初始化存储桶名称和 MinIO 客户端。"""
        self.bucket = settings.minio_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            region=settings.minio_region,
        )
        public = urlsplit(settings.minio_public_url)
        if public.scheme not in ("http", "https") or not public.netloc or public.path.rstrip("/") or public.query or public.fragment or public.username:
            raise ValueError("MINIO_PUBLIC_URL 必须是 S3 API 的 http(s) 根地址，不含路径、凭据或查询参数")
        # Signing is local: use the externally reachable host and an explicit region.
        self.public_client = Minio(
            public.netloc, access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key, secure=public.scheme == "https",
            region=settings.minio_region,
        )

    def ensure_bucket(self) -> None:
        """确保桶存在并移除匿名读取策略。失败时不以公开模式继续启动。"""
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
        try:
            self.client.delete_bucket_policy(self.bucket)
        except S3Error as exc:
            if exc.code not in ("NoSuchBucketPolicy", "NoSuchPolicy"):
                raise

    def upload_bytes(self, object_name: str, content: bytes, content_type: str | None = None) -> str:
        """上传私有对象，返回用于数据库保存的稳定引用。"""
        self.client.put_object(
            self.bucket,
            object_name,
            BytesIO(content),
            length=len(content),
            content_type=content_type or "application/octet-stream",
        )
        return self.reference_url(object_name)

    def reference_url(self, object_name: str) -> str:
        """稳定对象引用；访问图片时需另外生成短时签名。"""
        return f"{settings.minio_public_url.rstrip('/')}/{self.bucket}/{quote(object_name)}"

    def signed_url(self, object_name: str) -> str:
        return self.public_client.presigned_get_object(
            self.bucket, object_name, expires=timedelta(seconds=settings.image_url_expire_seconds),
        )

    def object_name(self, reference: str) -> str:
        """只解析当前桶；签名参数不充当所有权证明，调用方必须查所有者。"""
        expected = urlsplit(self.reference_url(""))
        supplied = urlsplit(reference)
        if (
            supplied.scheme not in ("http", "https")
            or (supplied.scheme, supplied.netloc) != (expected.scheme, expected.netloc)
            or not supplied.path.startswith(expected.path)
            or supplied.fragment
        ):
            raise ValueError("图片地址不是当前存储中的上传照片")
        name = unquote(supplied.path[len(expected.path):])
        if not name or "\\" in name or any(ord(c) < 32 for c in name) or any(part in ("", ".", "..") for part in name.split("/")):
            raise ValueError("图片地址无效")
        return name

    def read_image_bytes(self, public_url: str, max_bytes: int) -> bytes:
        """校验对象引用属于当前存储桶后，通过 MinIO 读取对象字节。

        最多读取 max_bytes + 1 字节，由调用方判断是否超限。
        无论读取成功或失败，都关闭响应并释放连接。
        """
        object_name = self.object_name(public_url)
        response = self.client.get_object(self.bucket, object_name)
        try:
            # 比上限多读一个字节，以便发现超限文件，不依赖对象大小元数据。
            return response.read(max_bytes + 1)
        finally:
            response.close()
            response.release_conn()


_storage: ObjectStorage | None = None


def get_storage() -> ObjectStorage:
    """按需创建并复用当前进程的对象存储客户端。"""
    global _storage
    if _storage is None:
        _storage = ObjectStorage()
    return _storage
