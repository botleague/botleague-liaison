import time

from botleague_helpers.key_value_store import get_key_value_store
from box import Box

from bot_eval import get_eval_db_key


def handle_results_request(request):
    data = Box(request.json)
    eval_key = data.get('eval_key', '')
    results = data.get('results', Box())
    results.finished = time.time()
    if not eval_key:
        request.response.status = 400
        results.error = 'eval_key must be in JSON data payload'
    elif 'error' in data:
        request.response.status = 400
        results.error = data.error
    elif 'results' not in data:
        request.response.status = 400
        results.error = 'No "results" found in request'
    else:
        db_key = get_eval_db_key(eval_key)
        # eval_key is secret
        kv = get_key_value_store()
        eval_data = Box(kv.get(db_key))
        if not eval_data:
            request.response.status = 400
            results.error = 'Could not find evaluation with that key'
        else:
            add_eval_data_to_results(eval_data, results)
    # TODO: Post results to gist


def add_eval_data_to_results(eval_data: Box, results: Box):
    """
    Handles results POSTS from problem evaluators at the
    """
    # Get the eval_data using the result.eval_key

    results.username = eval_data.username
    results.botname = eval_data.botname
    results.problem_id = eval_data.problem_id
    results.started = eval_data.started
    results.league_commit_sha = eval_data.league_commit_sha
    results.source_commit = eval_data.source_commit
    results.seed = eval_data.seed
