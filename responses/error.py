from box import Box


class Error(Box):
    message: str
    http_status_code: int

    def __init__(self, http_status_code: int = None, message: str = '', *args,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.http_status_code = http_status_code
        self.message = message

    def __bool__(self):
        if self.message:
            return True
        else:
            return False
