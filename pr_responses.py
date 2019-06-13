from box import Box


class PrResponse:
    msg: str

    def __init__(self, msg):
        self.msg = msg


class ErrorPrResponse(PrResponse):
    pass


class StartedPrResponse(PrResponse):
    pass


class RegenPrResponse(PrResponse):
    pass


class IgnorePrResponse(PrResponse):
    pass


class EvalStartedPrResponse(StartedPrResponse):
    eval_data: Box = None

    def __init__(self, msg, eval_data):
        super().__init__(msg)
        self.eval_data = eval_data


class EvalErrorPrResponse(ErrorPrResponse):
    pass
