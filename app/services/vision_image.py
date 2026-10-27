import base64

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

    仅接收入口已经校验过归属的稳定引用，从当前私有 MinIO 存储读取。
    限制单张图片大小，并按实际内容设置 MIME 类型；失败时抛出可展示异常。
    """
    try:
        content = await run_in_threadpool(get_storage().read_image_bytes, url, MAX_IMAGE_BYTES)
    except Exception as exc:
        raise ImagePreparationError("无法读取餐食照片，请重新上传后再试") from exc
    if not content:
        raise ImagePreparationError("餐食照片为空，请重新上传")
    if len(content) > MAX_IMAGE_BYTES:
        raise ImagePreparationError("单张识别照片不能超过 10 MB，请压缩后重新上传")
    mime = _image_mime(content)
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"
