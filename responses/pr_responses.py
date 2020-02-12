from logs import log
from typing import Optional, List

from box import Box


class PrResponse:
    msg: str

    def __init__(self, msg):
        self.msg = truncate_pr_msg(msg)


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
        self.bot_evals = bot_evals


class NoBotsResponse(PrResponse):
    pass


class EvalErrorPrResponse(ErrorPrResponse):
    pass


def truncate_pr_msg(pr_msg):
    pr_msg = str(pr_msg)
    if len(pr_msg) >= 140:
        log.error(f'PR message {pr_msg} was longer than 140 chars, truncating')
        pr_msg = pr_msg[:139]
    return pr_msg