import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse
from supabase_auth.errors import AuthApiError
from postgrest.exceptions import APIError as PostgRESTAPIError
from pydantic import BaseModel

logger = logging.getLogger("oasis.exceptions")


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
class ErrorDetail(BaseModel):
    code: str
    message: str


class OasisErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Base exception hierarchy
# ---------------------------------------------------------------------------
class OasisException(Exception):
    """Base para todas las excepciones controladas del sistema."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class UnauthorizedError(OasisException):
    def __init__(self, message: str = "No autorizado"):
        super().__init__(
            code="auth_unauthorized",
            message=message,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class ForbiddenError(OasisException):
    def __init__(self, message: str = "Acceso denegado"):
        super().__init__(
            code="auth_forbidden",
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
        )


class NotFoundError(OasisException):
    def __init__(self, resource: str):
        super().__init__(
            code="not_found",
            message=f"{resource} no encontrado",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class ConflictError(OasisException):
    def __init__(self, message: str = "El recurso ya existe"):
        super().__init__(
            code="conflict",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


class ValidationError(OasisException):
    def __init__(self, message: str = "Datos de entrada invalidos"):
        super().__init__(
            code="validation_error",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


# ---------------------------------------------------------------------------
# OasisException handler
# ---------------------------------------------------------------------------
async def oasis_exception_handler(request: Request, exc: OasisException):
    return JSONResponse(
        status_code=exc.status_code,
        content=OasisErrorResponse(
            error=ErrorDetail(code=exc.code, message=exc.message)
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Supabase Auth (GoTrue) error mapping
# ---------------------------------------------------------------------------
AUTH_CODE_TO_STATUS: dict[str, tuple[int, str]] = {
    "invalid_credentials": (401, "auth_invalid_credentials"),
    "invalid_grant": (401, "auth_invalid_credentials"),
    "user_not_found": (401, "auth_user_not_found"),
    "email_not_confirmed": (403, "auth_email_not_confirmed"),
    "phone_not_confirmed": (403, "auth_phone_not_confirmed"),
    "user_banned": (403, "auth_user_banned"),
    "email_exists": (409, "auth_email_exists"),
    "phone_exists": (409, "auth_phone_exists"),
    "user_already_exists": (409, "auth_user_already_exists"),
    "weak_password": (422, "auth_weak_password"),
    "validation_failed": (422, "auth_validation_failed"),
    "over_request_rate_limit": (429, "auth_rate_limit"),
    "over_email_send_rate_limit": (429, "auth_rate_limit"),
}


async def auth_api_error_handler(request: Request, exc: AuthApiError):
    error_code = getattr(exc, "code", None) or ""
    error_message = getattr(exc, "message", None) or str(exc)

    mapped = AUTH_CODE_TO_STATUS.get(error_code)
    if mapped:
        http_status, oasis_code = mapped
    else:
        http_status = getattr(exc, "status", status.HTTP_400_BAD_REQUEST)
        oasis_code = f"auth_{error_code}" if error_code else "auth_provider_error"

    logger.warning("AuthApiError: %s (code=%s, status=%s)", error_message, error_code, http_status)

    return JSONResponse(
        status_code=http_status,
        content=OasisErrorResponse(
            error=ErrorDetail(code=oasis_code, message=error_message)
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# PostgREST error mapping
# ---------------------------------------------------------------------------
POSTGREST_CODE_TO_STATUS: dict[str, tuple[int, str]] = {
    "23505": (409, "db_unique_violation"),
    "23503": (409, "db_foreign_key_violation"),
    "23514": (422, "db_check_violation"),
    "23502": (422, "db_not_null_violation"),
    "42501": (403, "db_insufficient_privilege"),
    "42000": (403, "db_insufficient_privilege"),
    "PGRST301": (401, "db_jwt_expired"),
}


async def postgrest_error_handler(request: Request, exc: PostgRESTAPIError):
    pg_code = getattr(exc, "code", None) or ""
    error_message = getattr(exc, "message", None) or str(exc)

    mapped = POSTGREST_CODE_TO_STATUS.get(pg_code)
    if mapped:
        http_status, oasis_code = mapped
    else:
        http_status = status.HTTP_400_BAD_REQUEST
        oasis_code = f"db_{pg_code}" if pg_code else "db_error"

    logger.warning("PostgRESTAPIError: %s (code=%s, status=%s)", error_message, pg_code, http_status)

    return JSONResponse(
        status_code=http_status,
        content=OasisErrorResponse(
            error=ErrorDetail(code=oasis_code, message=error_message)
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Generic fallback handler
# ---------------------------------------------------------------------------
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content=OasisErrorResponse(
            error=ErrorDetail(code="internal_error", message="Error interno del servidor")
        ).model_dump(),
    )
