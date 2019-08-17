import time
from typing import Tuple, Optional

import github
from botleague_helpers.config import get_test_name_from_callstack, blconfig
from botleague_helpers.db import DB
from box import Box
from github import Github, PullRequestMergeStatus, GithubException
import github.Gist

from bot_eval import get_eval_db_key
import constants
from models.eval_data import get_eval_data, save_eval_data
import logging as log

from responses.error import Error
from utils import trigger_leaderboard_generation, get_botleague_db_store

log.basicConfig(level=log.INFO)


def handle_results_request(request) -> Tuple[Box, Box, Optional[str]]:
    """
    Handles results POSTS from problem evaluators at the end of evaluation
    """
    data = Box(request.json)
    db = get_botleague_db_store()
    error, results, eval_data, gist = process_results(data, db)
    eval_data.status = constants.EVAL_STATUS_COMPLETE
    save_eval_data(eval_data, db)

    if not error:
        error = merge_pull_request(eval_data.pull_request)

    if error:
        results.error = error

    return results, error, gist


def merge_pull_request(pull_request: Box) -> Error:
    error = Error()
    if blconfig.is_test or get_test_name_from_callstack():
        log.info('Skipping pr merge in test')
    else:
        log.info(f'Merging pull request {pull_request.to_json(indent=2)}')
        github_client = Github(blconfig.github_token)
        repo = github_client.get_repo(pull_request.base_full_name)
        pr = repo.get_pull(pull_request.number)
        try:
            merge_status = pr.merge('Automatically merged by Botleague')
            if not merge_status.merged:
                error.message = merge_status.message
                error.http_status_code = 400
        except GithubException as e:
            error.message = str(e)
            error.http_status_code = e.status

    if error:
        log.error(f'Error merging pull request '
                  f'{error.to_json(indent=2)}')

    return error


def post_results_to_gist(db, results) -> Optional[github.Gist.Gist]:
    if blconfig.is_test or get_test_name_from_callstack():
        log.info('DETECTED TEST MODE: Not uploading results.')
        ret = None
    else:
        github_client = Github(
            db.get(constants.BOTLEAGUE_RESULTS_GITHUB_TOKEN_NAME))
        ret = github_client.get_user().create_gist(
            public=True,
            files={'results.json': github.InputFileContent(
                results.to_json(indent=2))},
            description='Automatically uploaded by botleague liaison')
    return ret


def process_results(result_payload: Box,
                    db: DB) -> Tuple[Error, Box, Box, Optional[str]]:
    eval_key = result_payload.get('eval_key', '')
    results = result_payload.get('results', Box())
    results.finished = time.time()
    error = Error()
    eval_data = Box()
    gist = None
    if not eval_key:
        error.http_status_code = 400
        error.message = 'eval_key must be in JSON data payload'
    else:
        eval_data = get_eval_data(eval_key, db)
        if not eval_data:
            error.http_status_code = 400
            error.message = 'Could not find evaluation with that key'
        elif eval_data.status == constants.EVAL_STATUS_STARTED:
            error.http_status_code = 400
            error.message = 'This evaluation has not been confirmed'
        elif eval_data.status == constants.EVAL_STATUS_COMPLETE:
            error.http_status_code = 400
            error.message = 'This evaluation has already been processed'
        elif eval_data.status == constants.EVAL_STATUS_CONFIRMED:
            if 'error' in result_payload:
                error.http_status_code = 500
                error.message = result_payload.error
            elif 'results' not in result_payload:
                error.http_status_code = 400
                error.message = 'No "results" found in request'
            add_eval_data_to_results(eval_data, results)
            gist = post_results_to_gist(db, results)
            gist = gist.html_url if gist else None
            trigger_leaderboard_generation()
        else:
            error.http_status_code = 400
            error.message = 'Eval data status unknown %s' % eval_data.status

    return error, results, eval_data, gist


def add_eval_data_to_results(eval_data: Box, results: Box):
    results.username = eval_data.username
    results.botname = eval_data.botname
    results.problem = eval_data.problem_id
    results.started = eval_data.started
    results.league_commit_sha = eval_data.league_commit_sha
    results.source_commit = eval_data.source_commit
    results.seed = eval_data.seed
    results.utc_timestamp = time.time()
