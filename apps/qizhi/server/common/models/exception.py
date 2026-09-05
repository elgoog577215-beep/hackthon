class BizException(Exception):
    """业务异常"""
    def __init__(self, error: str):
        self.error = error
        super().__init__(self.error)


class SystemException(Exception):
    """系统异常"""
    def __init__(self, error: str):
        self.error = error
        super().__init__(self.error)


class AuthException(Exception):
    """认证异常"""
    def __init__(self, error: str):
        self.error = error
        super().__init__(self.error)
