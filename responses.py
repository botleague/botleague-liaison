class Response:
    msg: str

    def __init__(self, msg):
        self.msg = msg


class ErrorResponse(Response):
    pass


class StartedResponse(Response):
    pass

