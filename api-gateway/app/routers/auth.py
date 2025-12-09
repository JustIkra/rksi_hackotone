"""
Authentication router.

Handles user registration, login, and profile management.
"""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_active_user, get_current_user
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import (
    LoginRequest,
    MessageResponse,
    PasswordChangeRequest,
    ProfileUpdateRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import (
    authenticate_user,
    change_user_password,
    create_access_token,
    create_user,
    update_user_profile,
)

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user with PENDING status.

    New users must be approved by an administrator before they can access the system.

    **Flow:**
    1. User registers with email, password, and optional full_name (ФИО)
    2. Account is created with status=PENDING
    3. Admin approves the user via `/admin/approve`
    4. User can now log in

    **Errors:**
    - 400: Email already registered
    - 422: Invalid email or weak password
    """
    try:
        user = await create_user(db, request.email, request.password, full_name=request.full_name)
        return UserResponse.model_validate(user)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except SQLAlchemyError as e:
        # Common cause: database not initialized or migrations not applied
        # Return 503 with actionable message instead of 500
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable or schema not initialized. Please run migrations (alembic upgrade head).",
        ) from e


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate user and set JWT token in httpOnly cookie.

    **Flow:**
    1. Verify email and password
    2. Check user status (must be ACTIVE)
    3. Generate JWT token
    4. Set token in httpOnly Secure cookie
    5. Return user info

    **Errors:**
    - 401: Invalid credentials
    - 403: User not active (PENDING or DISABLED)
    """
    try:
        user = await authenticate_user(db, request.email, request.password)
    except SQLAlchemyError as e:
        # Common cause: database not initialized or migrations not applied
        # Return 503 with actionable message instead of 500
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable or schema not initialized. Please run migrations (alembic upgrade head).",
        ) from e

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Check user status
    if user.status != "ACTIVE":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Account is {user.status}. Please contact an administrator.",
        )

    token = create_access_token(user.id, user.email, user.role)

    # Use Secure only when not in local dev (browsers ignore Secure over http)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=not settings.is_dev,  # In dev over HTTP, allow non-Secure for local testing
        samesite="lax",
        max_age=1800,  # 30 minutes (matches access_token_ttl_min)
    )

    return TokenResponse(
        message="Login successful",
        user=UserResponse.model_validate(user),
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response):
    """
    Log out current user by clearing the authentication cookie.

    **Flow:**
    1. Clear the access_token cookie
    2. Client is no longer authenticated

    **Note:** This is a client-side logout. The JWT token remains valid until it expires.
    For server-side session invalidation, implement a token blacklist.
    """
    response.delete_cookie(key="access_token")

    return MessageResponse(message="Logged out successfully")


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user),
):
    """
    Get current authenticated user profile.

    **Requires:** Valid JWT token in cookie

    **Errors:**
    - 401: Not authenticated or invalid token
    """
    return UserResponse.model_validate(current_user)


@router.get("/me/check-active", response_model=UserResponse)
async def check_active(
    current_user: User = Depends(get_current_active_user),
):
    """
    Check if current user is ACTIVE.

    Use this endpoint to verify user has been approved before allowing access to protected resources.

    **Requires:** Valid JWT token + ACTIVE status

    **Errors:**
    - 401: Not authenticated
    - 403: User is PENDING or DISABLED
    """
    return UserResponse.model_validate(current_user)


@router.put("/me/profile", response_model=UserResponse)
async def update_profile(
    request: ProfileUpdateRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update current user profile (full_name).

    **Requires:** Valid JWT token + ACTIVE status

    **Request Body:**
    - full_name: User full name (ФИО) - optional

    **Errors:**
    - 401: Not authenticated
    - 403: User is not ACTIVE
    - 422: Invalid full_name format
    """
    try:
        updated_user = await update_user_profile(db, current_user.id, request.full_name)
        return UserResponse.model_validate(updated_user)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable or schema not initialized.",
        ) from e


@router.post("/me/change-password", response_model=MessageResponse)
async def change_password(
    request: PasswordChangeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change current user password.

    Verifies current password before updating to new password.

    **Requires:** Valid JWT token + ACTIVE status

    **Request Body:**
    - current_password: Current password for verification
    - new_password: New password (min 8 chars, at least one letter and one digit)

    **Errors:**
    - 400: Current password is incorrect
    - 401: Not authenticated
    - 403: User is not ACTIVE
    - 422: New password does not meet strength requirements
    """
    try:
        await change_user_password(db, current_user.id, request.current_password, request.new_password)
        return MessageResponse(message="Password changed successfully")

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable or schema not initialized.",
        ) from e
