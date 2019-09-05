from typing import Optional, List

from box import Box, BoxList


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
    eval_data: Optional[Box] = None

    def __init__(self, msg, eval_data):
        super().__init__(msg)
        self.eval_data = eval_data


class ProblemCIResponse(StartedPrResponse):
    bot_evals: Optional[List] = None

    def __init__(self, msg, bot_evals):
        super().__init__(msg)
        self.eval_data = bot_evals


class NoBotsResponse(PrResponse):
    pass


class EvalErrorPrResponse(ErrorPrResponse):
    pass
