import math
import sys
import time
from copy import deepcopy
from statistics import mean, median, stdev

from botleague_helpers.crypto import decrypt_symmetric
from botleague_helpers.reduce import try_reduce_async
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from typing import Tuple, Optional

import github
from botleague_helpers.config import get_test_name_from_callstack, blconfig
from botleague_helpers.utils import box2json, dbox
from botleague_helpers.db import DB, get_db
from box import Box, BoxList
from github import Github, GithubException
import github.Gist

from bot_eval import get_eval_db_key
import constants
from models.eval_data import get_eval_data, save_eval_data
from logs import log

from problem_ci import get_problem_ci_db_id, PROBLEM_CI_STATUS_FAILED, \
    PROBLEM_CI_STATUS_PASSED
from responses.error import Error
from responses.pr_responses import truncate_pr_msg
from utils import trigger_leaderboard_generation, get_liaison_db_store, dbox


@log.catch(reraise=True)
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
    eval_data.gist = gist
    if error:
        eval_data.error = error
    eval_data.results = results
    eval_data.results_at = SERVER_TIMESTAMP
    save_eval_data(eval_data, db)

    # Handle problem ci before saving to the aggregate bot scores
    # as we want to compare the new bot scores to the previous
    problem_ci, should_merge, ci_error = check_for_problem_ci(db, eval_data)

    if problem_ci:
        save_problem_ci_results(ci_error, db, error, eval_data, gist,
                                problem_ci, results, should_merge)
    else:
        # Just a normal bot eval
        update_pr_status(error, eval_data, results, gist)
        save_to_bot_scores(
            eval_data, eval_data.eval_key,
            Box(score=results.score, eval_key=eval_data.eval_key))

    # TODO: Save aggregate problem scores?

    if should_merge and not error:
        error = merge_pull_request(eval_data.pull_request)
    if error:
        results.error = error
    return error


def save_problem_ci_results(ci_error, db, error, eval_data, gist, problem_ci,
                            results, should_merge):
    if not should_merge:
        # If problem_ci fails, don't save to aggregate bot scores collection
        if ci_error:
            log.error('Problem CI failed, not saving to bots '
                        'official scores as this is likely an issue '
                        'with the new version of the problem.')
            problem_ci.status = PROBLEM_CI_STATUS_FAILED
            problem_ci.error = ci_error
            update_pr_status_problem_ci(ci_error, problem_ci, eval_data)
        else:
            log.info('Problem CI not yet finished')

    else:
        # Aggregate data from bot evals now that they're done
        gists = BoxList()
        for bot_eval_key in problem_ci.bot_eval_keys:
            bot_eval = db.get(get_eval_db_key(bot_eval_key))
            save_to_bot_scores(
                bot_eval, bot_eval.eval_key,
                Box(score=bot_eval.results.score,
                    eval_key=bot_eval.eval_key))
            gists.append(bot_eval.gist)
        problem_ci.gists = gists
        update_pr_status_problem_ci(error, problem_ci, eval_data)
        problem_ci.status = PROBLEM_CI_STATUS_PASSED
    db.set(problem_ci.id, problem_ci)

def save_to_bot_scores(eval_data, eval_key, new_score: Box):
    db = get_scores_db()
    score_id = get_scores_id(eval_data)
    orig = db.get(score_id)
    bot_scores = db.get(score_id) or dbox(Box(scores=[]))
    recorded = bot_scores and \
               any([b.eval_key == eval_key for b in bot_scores.scores])
    if not recorded:
        bot_scores.scores.append(new_score)
        score_values = [s.score for s in bot_scores.scores]
        if len(bot_scores) < 2:
            score_stdev = None
        else:
            score_stdev = stdev(score_values)
        new_bot_scores = Box(
            scores=bot_scores.scores,
            id=score_id,
            botname=eval_data.botname,
            username=eval_data.username,
            problem_id=eval_data.problem_id,
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
            save_to_bot_scores(eval_data, eval_key, new_score)
        else:
            log.success(f'Saved new bot scores '
                        f'{box2json(new_bot_scores)}')


def check_for_problem_ci(db: DB, eval_data: Box) -> Tuple[Box, bool, str]:
    """
    Check to see if PR is a problem CI and merge iff this is the last bot
    :return: Whether we should merge or not
    """
    # TODO: Test this (try_reduce_async is tested in helpers, but this
    #  method which calls it needs to be as well
    pr = eval_data.pull_request
    problem_ci_db_key = get_problem_ci_db_id(pr.number, pr.head_commit)
    problem_ci = db.get(problem_ci_db_key)
    error = ''
    if not problem_ci:
        should_merge = True
    else:
        def reduce():
            result = dbox(problem_ci)
            # Refetch all bots in case scores came in after initial request
            for bot_eval_key in problem_ci.bot_eval_keys:
                bot_eval = db.get(get_eval_db_key(bot_eval_key))
                past_bot_scores = get_past_bot_scores(bot_eval)
                bot_eval_no_eval_key = deepcopy(bot_eval)
                del bot_eval_no_eval_key['eval_key']
                log.info(f'Checking confidence interval for bot_eval '
                         f'{box2json(bot_eval)}\n'
                         f'past scores: {box2json(past_bot_scores)}')
                if bot_eval.results.errors:
                    result.error = str(bot_eval.results.errors)
                    log.error(result.error + ': bot details ' \
                        f'{box2json(bot_eval_no_eval_key)}')
                    return result
                in_interval, interval_info = score_within_confidence_interval(
                    bot_eval, past_bot_scores)
                if not in_interval:
                    result.error = f'Score for bot {bot_eval.results.score}' \
                        f' not within confidence interval ' \
                        f'{interval_info.low} to {interval_info.high}, ' \
                        f'mean: {interval_info.mean} ' \
                        f'problem CI failed'
                    log.error(result.error + ': bot details ' \
                        f'{box2json(bot_eval_no_eval_key)}')
                    return result
            else:
                log.success('Score for bot within confidence interval, '
                          'problem CI successful!')
                return result

        reduce_result = try_reduce_async(
            reduce_id=problem_ci_db_key,
            ready_fn=get_bots_done_fn(db, problem_ci.bot_eval_keys),
            reduce_fn=reduce)

        if not reduce_result:
            # Not ready
            should_merge = False
        elif reduce_result.error:
            error = reduce_result.error
            should_merge = False
        else:
            should_merge = True

    return problem_ci, should_merge, error


def score_within_confidence_interval(bot_eval: Box,
                                     past_bot_scores: Box) -> Tuple[bool, Box]:
    """
    Compare with current mean score and check within
    acceptable_score_deviation range.
    If only 1 score, roughly
    double the acceptable range, since we could
    have gone from min to max.
    Also, follow the 2-sided CI for a t-student distribution
    that gives ~2x the acceptable_score_deviation with infinite
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
    info = Box(mean=None, ci_high=None, ci_low=None,
               acceptable_score_deviation=None)

    if bot_eval.eval_key in [p.eval_key for p in past_bot_scores.scores]:
        log.warning('Score already recorded, this should not happen!')
        return True, info
    score = bot_eval.results.score
    acceptable_score_deviation = bot_eval.problem_def.acceptable_score_deviation
    if not past_bot_scores.scores:
        # If no previous scores, then we are the mean of the CI
        return True, info
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

    info.high = ci_high
    info.low = ci_low
    info.mean = past_bot_scores.mean
    info.acceptable_score_deviation = acceptable_score_deviation

    if math.nan in [ci_high, ci_low]:
        ret = True
    elif ci_low <= score <= ci_high:
        ret = True
    else:
        ret = False

    return ret, info



def get_bots_done_fn(db, bot_eval_keys) -> callable:
    def bots_done():
        for bot_eval_key in bot_eval_keys:
            bot = db.get(get_eval_db_key(bot_eval_key))
            log.info(f'Checking if bot is done... bot: {box2json(bot)}')
            if bot.status != constants.EVAL_STATUS_COMPLETE:
                log.info('Bot not done')
                return False
        else:
            log.info('All bots done!')
            return True
    return bots_done


def update_pr_status_problem_ci(error: Error, problem_ci: Box, eval_data: Box):
    if error:
        pr_msg = error
        pr_status = constants.PR_STATUS_ERROR
    else:
        pr_msg = 'Evaluation complete'
        pr_status = constants.PR_STATUS_SUCCESS
    league_repo = github.Github(blconfig.github_token).get_repo(
        eval_data.pull_request.base_full_name)
    league_commit = league_repo.get_commit(
        sha=eval_data.pull_request.head_commit)
    # status can be error, failure, pending, or success
    status = league_commit.create_status(
        pr_status,
        description=truncate_pr_msg(pr_msg),
        target_url=f'{constants.HOST}/problem_ci_status?id={problem_ci.id}',
        context='Botleague')
    log.info(f'Updated PR status {status}')
    return status


def update_pr_status(error, eval_data, results, gist):
    if error:
        results.error = error
        pr_msg = error
        pr_status = constants.PR_STATUS_ERROR
    else:
        pr_msg = 'Evaluation complete'
        pr_status = constants.PR_STATUS_SUCCESS
    repo = github.Github(blconfig.github_token).get_repo(
        eval_data.pull_request.base_full_name)
    commit = repo.get_commit(sha=eval_data.pull_request.head_commit)
    # status can be error, failure, pending, or success
    status = commit.create_status(
        pr_status,
        description=truncate_pr_msg(pr_msg),
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
                 f'{box2json(pull_request)}')
        github_client = Github(blconfig.github_token)
        repo = github_client.get_repo(pull_request.base_full_name)
        pr = repo.get_pull(pull_request.number)
        if dbox(pr.raw_data).mergeable_state == 'draft':
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
                  f'{box2json(pull_request)} '
                  f'Error: {box2json(error)}')

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
                    db: DB) -> Tuple[Error, Box, Box, Optional[str], bool]:
    eval_key = result_payload.get('eval_key', '')
    results = result_payload.get('results', Box())
    results.finished = time.time()
    error = Error()
    eval_data = Box()
    gist = None
    should_skip = False
    # Note that 200, 400, and 500 are the ONLY expected status codes.
    # Other codes will be retried by the worker in post_results_with_retries.
    # This is due to App Engine returning 409's on the rare occasion.
    # https://voyage.slack.com/archives/CJLS63AMD/p1571773377003400
    if not eval_key:
        error.http_status_code = 400
        error.message = 'eval_key must be in JSON data payload'
    else:
        eval_data = get_eval_data(eval_key, db)
        if not eval_data:
            error.http_status_code = 400
            error.message = 'Could not find evaluation with that key'
        elif eval_data.botleague_liaison_host != constants.HOST and \
                constants.ON_GAE:
            log.warning('Not processing results due to botleague liaison '
                        'host being overridden')
            should_skip = True
        elif eval_data.status == constants.EVAL_STATUS_STARTED:
            error.http_status_code = 400
            error.message = 'This evaluation has not been confirmed'
        elif eval_data.status == constants.EVAL_STATUS_COMPLETE:
            error.http_status_code = 400
            error.message = 'This evaluation has already been processed'
        elif eval_data.status == constants.EVAL_STATUS_CONFIRMED:
            if 'results' not in result_payload:
                error.http_status_code = 400
                error.message = 'No "results" found in request'
            elif dbox(results).errors:
                error.http_status_code = 500
                error.message = box2json(Box(results.errors))
            add_eval_data_to_results(eval_data, results)
            gist = post_results_to_gist(db, results)
            gist = gist.html_url if gist else None
            trigger_leaderboard_generation()
        else:
            error.http_status_code = 400
            error.message = 'Eval data status unknown %s' % eval_data.status

    return error, results, eval_data, gist, should_skip


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
    """
    :return: e.g. 'crizcraig#goodbot-on-deepdrive#unprotected_left'
    """

    # Forward slashes not allowed on firestore
    # https://stackoverflow.com/a/54918283/134077
    problem_id = eval.problem_id.replace('/', '#')

    ret = f'{eval.username}#{eval.botname}-on-{problem_id}'
    return ret


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


def get_past_bot_scores(bot_eval=None):
    ret = None
    if bot_eval:
        ret = get_scores_db().get(get_scores_id(bot_eval))
    if not ret:
        ret = Box(scores=[], means=None)
    return ret
