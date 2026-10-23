import base64
import binascii

from starlette.concurrency import run_in_threadpool

from app.services.storage import get_storage
from app.core.upload_limits import MAX_IMAGE_BYTES


class ImagePreparationError(ValueError):
    """图片准备异常：向用户返回可读提示，不包含存储凭据或图片内容。"""


def _image_mime(content: bytes) -> str:
    """根据文件头判断图片类型，避免扩展名与实际内容不一致。"""
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    raise ImagePreparationError("照片格式不支持，请上传 JPG、PNG、GIF 或 WebP 图片")


async def prepare_image_data_url(url: str) -> str:
    """将上传照片转换为视觉模型可直接读取的 Base64 Data URL。

    普通地址从当前 MinIO 存储读取；已有 Data URL 先解码校验再统一编码。
    限制单张图片大小，并按实际内容设置 MIME 类型；失败时抛出可展示异常。
    """
    if url.startswith("data:"):
        header, separator, encoded = url.partition(",")
        if not separator or not header.startswith("data:image/") or not header.endswith(";base64"):
            raise ImagePreparationError("图片 Base64 格式无效，请重新上传")
        if len(encoded) > 4 * ((MAX_IMAGE_BYTES + 2) // 3):
            raise ImagePreparationError("单张识别照片不能超过 10 MB，请压缩后重新上传")
        try:
            content = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ImagePreparationError("图片 Base64 格式无效，请重新上传") from exc
    else:
        try:
            # MinIO 使用同步客户端，在线程池中读取，避免阻塞异步请求。
            content = await run_in_threadpool(get_storage().read_image_bytes, url, MAX_IMAGE_BYTES)
        except Exception as exc:
            raise ImagePreparationError("无法读取餐食照片，请重新上传后再试") from exc
    if not content:
        raise ImagePreparationError("餐食照片为空，请重新上传")
    if len(content) > MAX_IMAGE_BYTES:
        raise ImagePreparationError("单张识别照片不能超过 10 MB，请压缩后重新上传")
    mime = _image_mime(content)
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"
