import hashlib
from urllib.parse import urlencode

from authlib.integrations.base_client.errors import OAuthError
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.responses import RedirectResponse

from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User, UserRole
from app.schemas.user import CurrentUserResponse
from app.services.access import audit

settings = get_settings()
oauth = OAuth()
oauth.register(
    name="google",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

router = APIRouter(prefix="/auth", tags=["authentication"])


def frontend_redirect(**params: str) -> RedirectResponse:
    query = urlencode(params)
    return RedirectResponse(f"{settings.frontend_origin}/?{query}")


@router.get("/google/login")
async def google_login(request: Request) -> RedirectResponse:
    """Begin Google OpenID Connect login using the configured callback URI."""
    return await oauth.google.authorize_redirect(request, settings.google_redirect_uri)


@router.get("/google/callback")
async def google_callback(
    request: Request, db: Session = Depends(get_db)
) -> RedirectResponse:
    """Create the bootstrap admin once, otherwise permit only provisioned users."""
    try:
        token = await oauth.google.authorize_access_token(request)
    except OAuthError:
        request.session.clear()
        return frontend_redirect(error="oauth_failed")
    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = await oauth.google.parse_id_token(request, token)

    email = (userinfo.get("email") or "").lower().strip()
    subject = userinfo.get("sub")
    if not email or not subject or not userinfo.get("email_verified"):
        return frontend_redirect(error="google_account_not_verified")

    user = db.scalar(select(User).where(User.google_subject == subject))
    if not user:
        user = db.scalar(select(User).where(User.email == email))

    bootstrap_email = (settings.bootstrap_admin_email or "").lower().strip()
    if not user and bootstrap_email and email == bootstrap_email:
        user = User(
            google_subject=subject,
            email=email,
            full_name=userinfo.get("name"),
            avatar_url=userinfo.get("picture"),
            role=UserRole.SUPER_ADMIN,
        )
        db.add(user)
        db.flush()
        audit(db, user, "bootstrap", "user", user.id)
        db.commit()
        db.refresh(user)

    if not user or not user.is_active:
        return frontend_redirect(error="not_authorized")

    if user.google_subject != subject:
        if not user.google_subject.startswith("pending:"):
            return frontend_redirect(error="identity_mismatch")
        user.google_subject = subject
        user.full_name = userinfo.get("name") or user.full_name
        user.avatar_url = userinfo.get("picture") or user.avatar_url
        db.commit()

    request.session.clear()
    audit(db, user, "login", "user", user.id)
    db.commit()
    request.session["user_id"] = user.id
    return frontend_redirect(login="success")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    user = db.get(User, user_id)
    if not user or not user.is_active:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return user


@router.get("/me", response_model=CurrentUserResponse)
def get_me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> None:
    request.session.clear()


def build_session_secret() -> str:
    """Derive a local signing secret without exposing credentials to the client.

    Replace this with a dedicated SESSION_SECRET before production deployment.
    """
    if settings.session_secret:
        return settings.session_secret
    if settings.environment == "production":
        raise RuntimeError("SESSION_SECRET is required in production.")
    return hashlib.sha256(
        f"adem-lms-session-v1:{settings.google_client_secret}".encode()
    ).hexdigest()
