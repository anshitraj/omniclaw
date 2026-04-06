from fastapi import HTTPException, status


class MCPException(HTTPException):
    def __init__(self, detail: str, status_code: int = status.HTTP_400_BAD_REQUEST):
        super().__init__(status_code=status_code, detail=detail)


class PaymentError(MCPException):
    pass


class GuardValidationError(PaymentError):
    def __init__(self, detail: str):
        super().__init__(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


class BudgetExceededError(GuardValidationError):
    def __init__(self, reason: str):
        super().__init__(f"Budget Violation: {reason}")


class UnauthorizedRecipientError(GuardValidationError):
    def __init__(self, recipient: str):
        super().__init__(f"Unauthorized Recipient: {recipient}")


class RateLimitExceededError(GuardValidationError):
    def __init__(self):
        super().__init__("Rate limit exceeded for autonomous payments")


class WalletNotFoundError(MCPException):
    def __init__(self, wallet_id: str):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Wallet {wallet_id} not found"
        )
