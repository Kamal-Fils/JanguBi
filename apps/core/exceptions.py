class ApplicationError(Exception):
    def __init__(self, message, extra=None):
        super().__init__(message)

        self.message = message
        self.extra = extra or {}


class OtpExpiredError(ApplicationError):
    pass


class OtpInvalidError(ApplicationError):
    pass


class OtpLockedError(ApplicationError):
    pass


class OtpRateLimitError(ApplicationError):
    pass


class TokenExpiredError(ApplicationError):
    pass


class TokenInvalidError(ApplicationError):
    pass
