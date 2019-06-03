from box import Box


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
    eval_data: Box = None

    def __init__(self, msg, eval_data):
        super().__init__(msg)
        self.eval_data = eval_data


class EvalErrorResponse(ErrorResponse):
    pass
