class ApiDomainError(Exception):
    retryable = False

    def __init__(self, *, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ResourceNotFoundError(ApiDomainError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=404)


class ResourceConflictError(ApiDomainError):
    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=409)


class AdminAuthenticationError(ApiDomainError):
    def __init__(self) -> None:
        super().__init__(
            code="ADMIN_AUTHENTICATION_FAILED",
            message="유효한 관리자 API 키가 필요합니다.",
            status_code=401,
        )


class AdminAuthenticationNotConfiguredError(ApiDomainError):
    def __init__(self) -> None:
        super().__init__(
            code="ADMIN_AUTHENTICATION_NOT_CONFIGURED",
            message="관리자 API 인증이 설정되지 않았습니다.",
            status_code=503,
        )


class InvalidAuditCursorError(ApiDomainError):
    def __init__(self) -> None:
        super().__init__(
            code="INVALID_AUDIT_CURSOR",
            message="감사 이력 조회 커서가 올바르지 않습니다.",
            status_code=400,
        )


class DemoProfileNotFoundError(ResourceNotFoundError):
    def __init__(self, demo_profile_id: str) -> None:
        super().__init__(
            code="DEMO_PROFILE_NOT_FOUND",
            message=f"Demo Profile을 찾을 수 없습니다: {demo_profile_id}",
        )


class CustomerSessionNotFoundError(ResourceNotFoundError):
    def __init__(self, session_id: str) -> None:
        super().__init__(
            code="CUSTOMER_SESSION_NOT_FOUND",
            message=f"고객 세션을 찾을 수 없습니다: {session_id}",
        )


class ConsentScopeNotFoundError(ResourceNotFoundError):
    def __init__(self, source_type: str) -> None:
        super().__init__(
            code="CONSENT_SCOPE_NOT_FOUND",
            message=f"동의 범위를 찾을 수 없습니다: {source_type}",
        )


class ConsentNotGrantedError(ResourceConflictError):
    def __init__(self, source_type: str) -> None:
        super().__init__(
            code="CONSENT_NOT_GRANTED",
            message=f"승인되지 않은 동의는 철회할 수 없습니다: {source_type}",
        )
