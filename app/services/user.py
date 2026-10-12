from uuid import UUID, uuid4
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt
import httpx
import bcrypt

from app.core.config import settings
from app.core.exceptions import BadRequest, InternalError
from app.models.user import User
from app.schemas.user import UserUpdate


WECHAT_CODE2SESSION = "https://api.weixin.qq.com/sns/jscode2session"


def _create_token(user_id: UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode({"sub": str(user_id), "exp": expire}, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def _mock_openid(code: str) -> str:
    return f"mock_{code}" if code != "mock" else "mock_openid"


async def _wechat_openid(code: str) -> str:
    async with httpx.AsyncClient() as client:
        resp = await client.get(WECHAT_CODE2SESSION, params={
            "appid": settings.wechat_appid,
            "secret": settings.wechat_secret,
            "js_code": code,
            "grant_type": "authorization_code",
        })
        data = resp.json()
    if errcode := data.get("errcode"):
        raise BadRequest(f"微信登录失败: {data.get('errmsg', '未知错误')}")
    return data["openid"]


async def login(db: AsyncSession, code: str) -> tuple[User, str, bool]:
    if not code:
        raise BadRequest("登录 code 不能为空")

    if settings.allow_mock_login and (code == "mock" or code.startswith("mock_")):
        openid = await _mock_openid(code)
    elif settings.wechat_secret:
        openid = await _wechat_openid(code)
    else:
        openid = await _mock_openid(code)

    result = await db.execute(select(User).where(User.openid == openid))
    user = result.scalar_one_or_none()

    if user:
        token = _create_token(user.id)
        return user, token, False

    user = User(openid=openid)
    db.add(user)
    await db.flush()
    token = _create_token(user.id)
    return user, token, True


def _normalize_account(account: str) -> str:
    return account.strip().lower()


def _hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise BadRequest("密码不能超过 72 个字节")
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


async def register_web_account(db: AsyncSession, account: str, password: str, nickname: str = "") -> tuple[User, str, bool]:
    normalized_account = _normalize_account(account)
    result = await db.execute(select(User).where(User.account == normalized_account))
    if result.scalar_one_or_none():
        raise BadRequest("该账号已被注册")

    # Keep `openid` populated for compatibility with the existing data model.
    user = User(
        openid=f"web_{uuid4().hex}",
        account=normalized_account,
        password_hash=_hash_password(password),
        nickname=nickname.strip(),
    )
    db.add(user)
    await db.flush()
    return user, _create_token(user.id), True


async def login_web_account(db: AsyncSession, account: str, password: str) -> tuple[User, str, bool]:
    normalized_account = _normalize_account(account)
    result = await db.execute(select(User).where(User.account == normalized_account))
    user = result.scalar_one_or_none()
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72 or not user or not user.password_hash or not bcrypt.checkpw(password_bytes, user.password_hash.encode("utf-8")):
        raise BadRequest("账号或密码错误")
    return user, _create_token(user.id), False


async def get_user(db: AsyncSession, user_id: UUID) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def update_user(db: AsyncSession, user_id: UUID, data: UserUpdate) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise BadRequest("用户不存在")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.flush()
    return user
