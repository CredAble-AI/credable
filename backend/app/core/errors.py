class ResourceNotFoundError(Exception):
    status_code = 404
    retryable = False

    def __init__(self, *, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


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
