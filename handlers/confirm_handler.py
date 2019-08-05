from botleague_helpers.key_value_store import get_key_value_store, \
    SimpleKeyValueStore
from box import Box

import constants
from models.eval_data import get_eval_data, save_eval_data
from responses.error import Error
from utils import get_botleague_kv_store


def handle_confirm_request(request):
    """
    Handles confirm POSTS from problem evaluators to ensure evaluation
    requests originated from the expected domain, e.g. liaison.botleague.io
    """
    data = Box(request.json)
    kv = get_botleague_kv_store()
    error, resp = process_confirm(data, kv)

    if error:
        resp.error = error

    return resp, error


def process_confirm(result_payload: Box, kv: SimpleKeyValueStore):
    eval_key = result_payload.get('eval_key', '')
    resp = Box(confirmed=False)
    error = Error()
    if not eval_key:
        error.http_status_code = 400
        error.message = 'eval_key must be in JSON data payload'
    else:
        eval_data = get_eval_data(eval_key, kv)
        if not eval_data:
            error.http_status_code = 400
            error.message = 'Could not find evaluation with that key'
        elif eval_data.status == constants.EVAL_STATUS_COMPLETE:
            error.http_status_code = 400
            error.message = 'This evaluation has already been processed'
        elif eval_data.status in [constants.EVAL_STATUS_STARTED,
                                  constants.EVAL_STATUS_CONFIRMED]:
            if 'error' in result_payload:
                error.http_status_code = 500
                error.message = result_payload.error
            else:
                # confirmed!
                resp.confirmed = True
                eval_data.status = constants.EVAL_STATUS_CONFIRMED
                save_eval_data(eval_data, kv)
        else:
            error.http_status_code = 400
            error.message = 'Eval data status unknown %s' % eval_data.status

    return error, resp


