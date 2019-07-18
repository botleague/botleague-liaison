from box import Box
from leaderboard_generator.botleague_gcp.key_value_store import \
    SimpleKeyValueStore

from bot_eval import get_eval_db_key


INVALID_DB_KEY_STATE_MESSAGE = 'Eval key in eval data were different. ' \
                               'Database in invalid state.'


def get_eval_data(eval_key, kv: SimpleKeyValueStore) -> Box:
    db_key = get_eval_db_key(eval_key)
    # eval_key is secret, do not make public anywhere!
    eval_data = Box(kv.get(db_key))
    if eval_data.eval_key != eval_key:
        raise RuntimeError(INVALID_DB_KEY_STATE_MESSAGE)
    return eval_data


def set_eval_data(eval_data: Box, kv: SimpleKeyValueStore):
    db_key = get_eval_db_key(eval_data.eval_key)
    # eval_key is secret, do not make public anywhere!
    kv.set(db_key, eval_data)