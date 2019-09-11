import math
import sys
import time
from statistics import mean, median, stdev

from botleague_helpers.crypto import decrypt_symmetric
from botleague_helpers.reduce import try_reduce_async
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from typing import Tuple, Optional

import github
from botleague_helpers.config import get_test_name_from_callstack, blconfig
from botleague_helpers.db import DB, get_db
from box import Box, BoxList
from github import Github, PullRequestMergeStatus, GithubException
import github.Gist

from bot_eval import get_eval_db_key
import constants
from handlers.pr_handler import PrProcessor
from models.eval_data import get_eval_data, save_eval_data
from loguru import logger as log

from problem_ci import get_problem_ci_db_key
from responses.error import Error
from utils import trigger_leaderboard_generation, get_liaison_db_store, dbox


def handle_results_request(request) -> Tuple[Box, Box, Optional[str]]:
    """
    Handles results POSTS from problem evaluators at the end of evaluation
    """
    data = Box(request.json)
    log.info(f'Handling results request {data.to_json(indent=2)}')
    db = get_liaison_db_store()
    error, results, eval_data, gist, should_skip = process_results(data, db)
    if not should_skip:
        error = save_results(db, error, eval_data, gist, results)

    return results, error, gist


def save_results(db, error, eval_data, gist, results):
    eval_data.status = constants.EVAL_STATUS_COMPLETE
    eval_data.results = Box(
        gist=gist,
        error=error,
        results=results, )
    eval_data.results_at = SERVER_TIMESTAMP
    save_eval_data(eval_data, db)
    update_pr_status(error, eval_data, results, gist)

    # Handle problem ci before saving bot scores as we want to compare the
    # new bot scores to the previous
    is_problem_ci, should_merge = handle_problem_ci(db, eval_data)

    # If problem_ci fails, don't save bot score

    if is_problem_ci and not should_merge:
        log.warning('Problem CI failed, not saving to bots official scores '
                    'as this is likely an issue with the new '
                    'version of the problem.')
    else:
        save_to_bot_scores(eval_data, eval_data.eval_key,  results.score)

    # TODO: Save aggregate problem scores?

    if should_merge and not error:
        error = merge_pull_request(eval_data.pull_request)
    if error:
        results.error = error
    return error


def save_to_bot_scores(eval_data, eval_key, score):
    db = get_scores_db()
    score_id = get_scores_id(eval_data)
    orig = db.get(score_id)
    bot_scores = db.get(score_id) or dbox(Box(scores=[]))
    recorded = bot_scores and \
               any([b.eval_key == eval_key for b in bot_scores.scores])
    if not recorded:
        bot_scores.scores.append(score)
        score_values = [s.score for s in bot_scores.scores]
        if len(bot_scores) < 2:
            score_stdev = None
        else:
            score_stdev = stdev(score_values)
        new_bot_scores = Box(scores=bot_scores.scores,
                              id=score_id,
                              updated_at=SERVER_TIMESTAMP,
                              mean=mean(score_values),
                              max=max(score_values),
                              min=min(score_values),
                              median=median(score_values),
                              stdev=score_stdev)
        if not orig:
            new_bot_scores.created_at = SERVER_TIMESTAMP
        if not db.cas(score_id, orig, new_bot_scores):
            log.warning('Race condition saving bot scores! Trying again.')
            save_to_bot_scores(eval_data, eval_key, score)
        else:
            log.success(f'Saved new bot scores '
                        f'{new_bot_scores.to_json(indent=2, default=str)}')


def handle_problem_ci(db: DB, eval_data: Box) -> Tuple[bool, bool]:
    """
    Check to see if PR is a problem CI and merge iff this is the last bot
    :return: Whether we should merge or not
    """
    pr = eval_data.pull_request
    problem_ci_db_key = get_problem_ci_db_key(pr.number, pr.head_commit)
    problem_ci = db.get(problem_ci_db_key)
    if not problem_ci:
        is_problem_ci = False
        should_merge = True
    else:
        is_problem_ci = True
        def reduce():
            # Refetch all bots in case scores came in after initial request
            for bot_eval_key in problem_ci.bot_eval_keys:
                bot_eval = db.get(get_eval_db_key(bot_eval_key))
                past_bot_scores = get_scores_db().get(get_scores_id(bot_eval))
                if not score_within_confidence_interval(bot_eval,
                                                        past_bot_scores):
                    return False
            else:
                return True

        reduce_result = try_reduce_async(
            reduce_id=problem_ci_db_key,
            ready_fn=get_bots_done_fn(db, problem_ci.bot_eval_keys),
            reduce_fn=reduce)
        if reduce_result:
            should_merge = True
        else:
            should_merge = False
    return is_problem_ci, should_merge


def score_within_confidence_interval(bot_eval: Box,
                                     past_bot_scores: Box) -> bool:
    """
    Compare with current mean score and check within
    acceptable_score_deviation range.
    If only 1 score, roughly
    double the acceptable range, since we could
    have gone from min to max.
    Also, follow the 2-sided CI for a t-student distribution
    that gives 2x the acceptable_score_deviation with infinite
    samples (i.e. ± acceptable_score_deviation)
    https://en.wikipedia.org/wiki/Student%27s_t-distribution#Table_of_selected_values
    https://stats.stackexchange.com/a/230185/18187

      n  Confidence Level  Multiplicative Factor
      2       0.95              12.71
      3       0.95               4.30
      4       0.95               3.18
      5       0.95               2.78
     infinity 0.95               1.96

    """
    if bot_eval.eval_key in [p.eval_key for p in past_bot_scores.scores]:
        log.warning('Score already recorded, this should not happen!')
        return True
    score = bot_eval.results.score
    acceptable_score_deviation = bot_eval.prob_def.acceptable_score_deviation
    if not past_bot_scores.scores:
        # If no previous scores, then we're good
        return True
    score_values = [b.score for b in past_bot_scores.scores]
    multiplier = {
        2: 12.71,
        3:  4.30,
        4:  3.18,
        5:  2.78,
    }.get(len(score_values) + 1, 1.96)

    diff_max = acceptable_score_deviation * multiplier / 2
    ci_low = past_bot_scores.mean - diff_max
    ci_high = past_bot_scores.mean + diff_max

    if math.nan in [ci_high, ci_low]:
        ret = True
    elif ci_low <= score <= ci_high:
        ret = True
    else:
        ret = False
    return ret



def get_bots_done_fn(db, bot_eval_keys) -> callable:
    def bots_done():
        for bot_eval_key in bot_eval_keys:
            bot = db.get(get_eval_db_key(bot_eval_key))
            if bot.status != constants.EVAL_STATUS_COMPLETE:
                return False
        else:
            return True
    return bots_done


def update_pr_status(error, eval_data, results, gist):
    if error:
        results.error = error
        pr_msg = error
        pr_status = constants.CI_STATUS_ERROR
    else:
        # TODO: Fan in all problem evals and set pending until they are all
        #   successful
        pr_msg = 'Evaluation complete'
        pr_status = constants.CI_STATUS_SUCCESS
    repo = github.Github(blconfig.github_token).get_repo(
        eval_data.pull_request.base_full_name)
    commit = repo.get_commit(sha=eval_data.pull_request.head_commit)
    # status can be error, failure, pending, or success
    status = commit.create_status(
        pr_status,
        description=pr_msg,
        target_url=gist,
        context='Botleague')
    log.info(f'Updated PR status {status}')
    return status


def merge_pull_request(pull_request: Box) -> Error:
    error = Error()
    if blconfig.is_test or get_test_name_from_callstack():
        log.info('Skipping pr merge in test')
    else:
        log.info(f'Merging pull request '
                 f'{pull_request.to_json(indent=2, default=str)}')
        github_client = Github(blconfig.github_token)
        repo = github_client.get_repo(pull_request.base_full_name)
        pr = repo.get_pull(pull_request.number)
        if dbox(pr.raw_data).draft:
            log.info('Pull request is draft, not trying to merge')
        else:
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
                  f'{error.to_json(indent=2, default=str)}')

    return error


def post_results_to_gist(db, results) -> Optional[github.Gist.Gist]:
    if blconfig.is_test or get_test_name_from_callstack():
        log.info('DETECTED TEST MODE: Not uploading results.')
        ret = None
    else:
        github_client = Github(
            decrypt_symmetric(
                db.get(constants.BOTLEAGUE_RESULTS_GITHUB_TOKEN_NAME)))
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


def get_scores_id(eval):
    return f'{eval.username}#{eval.botname}'


def collect_bot_scores(docker_tag=
                       'deepdriveio/deepdrive:bot_domain_randomization'):
    """
    Catches up bot scores using deepdrive_jobs. This is a violation of
    data boundaries across deepdrive and botleague, and won't be possible
    for future independent problem providers. We are now storing results
    in the bot_eval data as well, to avoid such problems in the future.
    Alternatively, we could have just downloaded all results from
    gist/botleague-results which is a source of truth, but this was easier.
    """
    job_db = get_db('deepdrive_jobs')
    ldb = get_liaison_db_store()
    for job in job_db.where('eval_spec.docker_tag', '==', docker_tag):
        eval_key = job.eval_spec.eval_key
        eval_data = ldb.get(get_eval_db_key(eval_key))
        score = Box(score=job.results.score, eval_key=eval_key)
        save_to_bot_scores(eval_data, eval_key, score)


def get_scores_db():
    return get_db('botleague_liaison_bot_scores')


if __name__ == '__main__':
    if 'collect_bot_scores' in sys.argv:
          collect_bot_scores()
