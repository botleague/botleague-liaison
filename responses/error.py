from box import Box


class Error(Box):
    message: str
    http_status_code: int

    def __init__(self, http_status_code: int = 200, message: str = '', *args,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.http_status_code = http_status_code
        self.message = message

    def __bool__(self):
        if self.message or self.http_status_code != 200:
            return True
        else:
            return False
