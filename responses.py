class Response:
    msg: str

    def __init__(self, msg):
        self.msg = msg


class ErrorResponse(Response):
    pass


class StartedResponse(Response):
    pass


class RegenResponse(Response):
    pass


class IgnoreResponse(Response):
    pass


class EvalStartedResponse(StartedResponse):
    pass


class EvalErrorResponse(ErrorResponse):
    pass
