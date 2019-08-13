from botleague_helpers.db import DB
from box import Box
from bot_eval import get_eval_db_key


INVALID_DB_KEY_STATE_MESSAGE = 'Eval key in eval data were different. ' \
                               'Database in invalid state.'


def get_eval_data(eval_key, kv: DB) -> Box:
    db_key = get_eval_db_key(eval_key)
    # eval_key is secret, do not make public anywhere!
    eval_data = Box(kv.get(db_key))
    if eval_data.eval_key != eval_key:
        raise RuntimeError(INVALID_DB_KEY_STATE_MESSAGE)
    return eval_data


def save_eval_data(eval_data: Box, kv: DB):
    db_key = get_eval_db_key(eval_data.eval_key)
    # eval_key is secret, do not make public anywhere!
    kv.set(db_key, eval_data)
