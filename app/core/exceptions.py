from fastapi import HTTPException
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED, HTTP_404_NOT_FOUND, HTTP_500_INTERNAL_SERVER_ERROR


class AppException(HTTPException):
    def __init__(self, status_code: int, code: int, message: str):
        self.code = code
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


class BadRequest(AppException):
    def __init__(self, message: str = "参数错误"):
        super().__init__(HTTP_400_BAD_REQUEST, HTTP_400_BAD_REQUEST, message)


class Unauthorized(AppException):
    def __init__(self, message: str = "未授权"):
        super().__init__(HTTP_401_UNAUTHORIZED, HTTP_401_UNAUTHORIZED, message)


class NotFound(AppException):
    def __init__(self, message: str = "资源不存在"):
        super().__init__(HTTP_404_NOT_FOUND, HTTP_404_NOT_FOUND, message)


class InternalError(AppException):
    def __init__(self, message: str = "服务器内部错误"):
        super().__init__(HTTP_500_INTERNAL_SERVER_ERROR, HTTP_500_INTERNAL_SERVER_ERROR, message)
