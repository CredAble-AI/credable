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


class DemoCaseNotFoundError(ResourceNotFoundError):
    def __init__(self, demo_case_id: str) -> None:
        super().__init__(
            code="DEMO_CASE_NOT_FOUND",
            message=f"Demo Case를 찾을 수 없습니다: {demo_case_id}",
        )


class CaseNotFoundError(ResourceNotFoundError):
    def __init__(self, case_id: str) -> None:
        super().__init__(
            code="CASE_NOT_FOUND",
            message=f"Case를 찾을 수 없습니다: {case_id}",
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
