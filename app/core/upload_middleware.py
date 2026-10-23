"""Bound upload bodies before the multipart parser spools files to disk."""

from starlette.formparsers import MultiPartException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.upload_limits import MAX_IMAGE_BYTES, MAX_UPLOAD_IMAGES, MULTIPART_OVERHEAD_BYTES


class _UploadTooLarge(MultiPartException):
    """Also triggers Starlette's multipart temporary-file cleanup."""


class UploadBodyLimitMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "").rstrip("/")
        root_path = scope.get("root_path", "").rstrip("/")
        if root_path and path.startswith(root_path + "/"):
            path = path[len(root_path):]
        limits = {
            "/api/v1/upload": MAX_IMAGE_BYTES + MULTIPART_OVERHEAD_BYTES,
            "/api/v1/upload/images": MAX_UPLOAD_IMAGES * MAX_IMAGE_BYTES + MULTIPART_OVERHEAD_BYTES,
        }
        if scope["type"] != "http" or scope["method"] != "POST" or path not in limits:
            await self.app(scope, receive, send)
            return

        limit = limits[path]
        response = JSONResponse(
            status_code=413,
            content={"code": 413, "message": "上传请求过大，请减少照片数量或压缩照片", "data": None},
        )
        for name, value in scope["headers"]:
            if name.lower() == b"content-length":
                try:
                    declared_size = int(value)
                    if declared_size < 0:
                        raise ValueError
                except ValueError:
                    await JSONResponse(
                        status_code=400,
                        content={"code": 400, "message": "无效的 Content-Length", "data": None},
                    )(scope, receive, send)
                    return
                if declared_size > limit:
                    await response(scope, receive, send)
                    return

        received = 0
        exceeded = False

        async def limited_receive() -> Message:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _UploadTooLarge("上传请求过大")
            return message

        async def limited_send(message: Message) -> None:
            # FastAPI may translate the parser error to 400; emit a consistent 413 instead.
            if not exceeded:
                await send(message)

        try:
            await self.app(scope, limited_receive, limited_send)
        except _UploadTooLarge:
            pass
        if exceeded:
            await response(scope, receive, send)
