import json
from io import BytesIO
from urllib.parse import quote, unquote, urlsplit

from minio import Minio

from app.core.config import settings


class ObjectStorage:
    """封装用户上传文件的 MinIO 存储、公开地址生成及受限读取。"""

    def __init__(self) -> None:
        """根据应用配置初始化存储桶名称和 MinIO 客户端。"""
        self.bucket = settings.minio_bucket
        self.client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )

    def ensure_bucket(self) -> None:
        """确保上传存储桶存在，并为桶内对象设置公开读取策略。"""
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
        self.client.set_bucket_policy(self.bucket, self._public_read_policy())

    def upload_bytes(self, object_name: str, content: bytes, content_type: str | None = None) -> str:
        """上传二进制文件并返回公开访问地址；未提供类型时使用通用二进制类型。"""
        self.client.put_object(
            self.bucket,
            object_name,
            BytesIO(content),
            length=len(content),
            content_type=content_type or "application/octet-stream",
        )
        return self.public_url(object_name)

    def public_url(self, object_name: str) -> str:
        """拼接对象的公开地址，对中文和空格等路径字符进行 URL 编码。"""
        return f"{settings.minio_public_url.rstrip('/')}/{self.bucket}/{quote(object_name)}"

    def read_image_bytes(self, public_url: str, max_bytes: int) -> bytes:
        """校验公开地址属于当前存储桶后，通过 MinIO 读取对象字节。

        最多读取 max_bytes + 1 字节，由调用方判断是否超限。
        无论读取成功或失败，都关闭响应并释放连接。
        """
        expected = urlsplit(self.public_url(""))
        supplied = urlsplit(public_url)
        if (
            supplied.scheme not in ("http", "https")
            or (supplied.scheme, supplied.netloc) != (expected.scheme, expected.netloc)
            or not supplied.path.startswith(expected.path)
        ):
            raise ValueError("图片地址不是当前存储中的上传照片")
        object_name = unquote(supplied.path[len(expected.path):])
        if not object_name or any(part in ("", ".", "..") for part in object_name.split("/")):
            raise ValueError("图片地址无效")
        response = self.client.get_object(self.bucket, object_name)
        try:
            # 比上限多读一个字节，以便发现超限文件，不依赖对象大小元数据。
            return response.read(max_bytes + 1)
        finally:
            response.close()
            response.release_conn()

    def _public_read_policy(self) -> str:
        """生成仅允许匿名读取当前桶内对象的 JSON 策略。"""
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
    """按需创建并复用当前进程的对象存储客户端。"""
    global _storage
    if _storage is None:
        _storage = ObjectStorage()
    return _storage
