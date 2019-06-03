import random
import time
import uuid
from os.path import basename
from typing import List, Union

from box import Box

import constants
import github
import requests
from botleague_helpers.config import blconfig, get_test_name_from_callstack
from botleague_helpers.key_value_store import SimpleKeyValueStore
from github import Repository
from responses import ErrorResponse, StartedResponse, RegenResponse, \
    IgnoreResponse, Response, EvalErrorResponse, EvalStartedResponse
from tests.mockable import Mockable
from utils import read_file, get_str_or_box

from utils import generate_rand_alphanumeric


class BotEvalBase:
    botname: str
    changed_filenames: List[str]
    user_or_org: str
    base_repo: Repository
    head_repo: Repository
    pr_event: Box
    seed: int

    def __init__(self, botname, changed_filenames, user_or_org, base_repo,
                 head_repo, pull_request):
        super().__init__()  # Support multiple inheritance
        self.botname = botname
        self.changed_filenames: List[str] = changed_filenames
        self.user_or_org = user_or_org
        self.base_repo = base_repo
        self.head_repo = head_repo
        self.pr_event = pull_request
        self.seed = random.choice(range(1, 10 ** 6))

    def eval(self) -> Union[Response, List[Response]]:
        bot_def_filenames = []
        bot_readme_filenames = []
        for filename in self.changed_filenames:
            if filename.endswith(constants.BOT_DEFINITION_FILENAME):
                bot_def_filenames.append(filename)
            elif filename.endswith(constants.README_FILENAME):
                bot_readme_filenames.append(filename)

        # Do evaluations
        if bot_def_filenames:
            if len(bot_def_filenames) > 1:
                ret = ErrorResponse('Only one bot per pull request allowed')
            else:
                ret = self.eval_bot(bot_def_filenames[0])
        elif bot_readme_filenames:
            # TODO: Should just be one passed in, but can double verify like above
            ret = ErrorResponse('Only one bot per pull request allowed')
        else:
            ret = ErrorResponse('Unsupported bot files changed %r' %
                                self.changed_filenames)
        return ret

        # TODO: Copy the docker image over to GCR
        # TODO: Handle cases where only readme changes

    def eval_bot(self, bot_def_filename) -> Union[Response, List[Response]]:
        bot_def = self.github_get(self.head_repo, bot_def_filename)
        source_commit = bot_def.source_commit

        github_prefix = 'https://github.com/'

        if not source_commit.startswith(github_prefix):
            return ErrorResponse('source_commit does not start with ' +
                                 github_prefix)

        # Validate that user_or_org matches source_commit and json_commit.
        source_commit_user = source_commit[
                             len(github_prefix):].split('/')[0]

        # TODO: Get the botname from the JSON commit path. It does not have to match
        #   the source_commit, i.e. deepdrive agents.

        if source_commit_user.lower() != self.user_or_org.lower():
            return ErrorResponse('Bot directory does not match user or org name'
                                 'on source repo, aborting')
        problem_ids = bot_def.problems
        prob_responses = self.eval_bots_problems(problem_ids, bot_def)
        return prob_responses

    def eval_bots_problems(self, problem_ids, bot_def) -> List[Response]:
        responses = []
        for problem_id in problem_ids:
            problem_def_url = '%s/%s/%s' % (
                constants.PROBLEMS_DIR, problem_id,
                constants.PROBLEM_DEFINITION_FILENAME)
            # Ensure the problem exists
            problem_def = self.github_get(self.base_repo, problem_def_url)
            if not problem_def:
                # Problem does not exist
                responses.append(
                    EvalErrorResponse('Problem does not exist %s' %
                                      problem_id))
            else:
                # Trigger the eval at the problem endpoint
                resp = self.trigger_single_eval(bot_def, problem_def,
                                                problem_id)
                responses.append(resp)
        return responses

    def trigger_single_eval(self, bot_def, problem_def, problem_id) -> Response:
        endpoint = problem_def.endpoint
        eval_key = generate_rand_alphanumeric(25)
        eval_id = generate_rand_alphanumeric(25)
        eval_data = self.get_eval_data(eval_id, eval_key, problem_id, bot_def)
        resp = self.request_eval(endpoint, eval_data)
        return resp

    @staticmethod
    def request_eval(endpoint, eval_data) -> Response:
        raise NotImplementedError()

    def get_eval_data(self, eval_id, eval_key, problem_id, bot_def) -> Box:
        pull_number = self.pr_event.number
        pull_url = self.pr_event.url
        pull_request_updated_at = self.pr_event.updated_at
        merge_commit_sha = self.pr_event.merge_commit_sha
        head_commit = self.pr_event.head.sha
        base_commit = self.pr_event.base.sha
        head_full_name = self.pr_event.head.repo.full_name
        base_full_name = self.pr_event.base.repo.full_name
        now = time.time()
        eval_data = Box(eval_key=eval_key,
                        eval_id=eval_id,
                        seed=self.seed,
                        problem_id=problem_id,
                        botname=self.botname,
                        username=self.user_or_org,
                        status=constants.EVAL_STATUS_STARTED,
                        started=now,
                        source_commit=bot_def.source_commit,
                        json_commit=self.pr_event.head.sha,
                        pull_request=dict(
                            url=pull_url,
                            number=pull_number,
                            updated_at=pull_request_updated_at,
                            merge_commit_sha=merge_commit_sha,
                            head_commit=head_commit,
                            head_full_name=head_full_name,
                            base_commit=base_commit,
                            base_full_name=base_full_name,
                        ), )
        return eval_data

    def github_get(self, repo, filename):
        raise NotImplementedError()


class BotEval(BotEvalBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def github_get(self, repo, filename):
        from utils import get_from_github
        return get_from_github(repo, filename)

    @staticmethod
    def request_eval(endpoint: str, eval_data: Box) -> Response:
        try:
            endpoint_resp = requests.post(endpoint, json=eval_data.to_json(),
                                          timeout=10)
        except requests.exceptions.Timeout:
            ret = EvalErrorResponse(
                'Endpoint %s took too long to respond' % endpoint)
        else:
            # Yay, we did not timeout!
            if endpoint_resp.status_code != 200:
                ret = EvalErrorResponse(
                    'Endpoint %s failed with HTTP %r, response body was %s'
                    % (endpoint, endpoint_resp.status_code,
                       endpoint_resp.content))
            else:
                kv = SimpleKeyValueStore()
                db_key = get_eval_db_key(eval_data)
                kv.set(db_key, eval_data)
                # TODO: Now we wait for a /confirm and /results request with the
                #   eval_key
                ret = EvalStartedResponse('Started evaluation at %s' % endpoint,
                                          eval_data)
        return ret


def get_eval_db_key(eval_data):
    return '%s_%s' % (constants.ONGOING_EVALUATIONS_KEY_PREFIX,
                      eval_data.eval_key)


class BotEvalMock(BotEvalBase, Mockable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def github_get(self, _repo, filename):
        filepath = self.get_test_filename(filename)
        content_str = read_file(filepath)
        ret = get_str_or_box(content_str, filepath)
        return ret

    @staticmethod
    def request_eval(endpoint: str, eval_data: Box) -> Response:
        assert eval_data.eval_key != eval_data.eval_id
        return EvalStartedResponse('Mock eval - nothing happening.', eval_data)


def get_bot_eval(use_mock):
    if use_mock or blconfig.is_test or get_test_name_from_callstack():
        # Redundant guard rails
        return BotEvalMock
    else:
        return BotEval


def process_changed_bot(
        base_repo, botname_dirs, changed_filenames, head_repo, pull_request,
        user_dirs, changed_filetypes, from_mock) -> \
        (Union[Response, List[Response]], bool):
    should_gen = False
    user_dirs = list(user_dirs)
    if len(user_dirs) > 1:
        resp = ErrorResponse(
            'Can only submit bots for one user at a time')
    elif len(botname_dirs) > 1:
        resp = ErrorResponse('Can only submit one bot at a time')
    else:
        user_or_org = user_dirs[0]
        botname = botname_dirs[0]
        if ['md'] == list(changed_filetypes):
            # Just a docs/readme change. Trigger leaderboard gen.
            should_gen = True
            resp = RegenResponse('Markdown only change detected, '
                                 'regenerating leaderboards')
        else:
            # Trigger bot evaluation
            evaluator = get_bot_eval(use_mock=from_mock)(
                botname=botname,
                changed_filenames=changed_filenames,
                user_or_org=user_or_org,
                base_repo=base_repo, head_repo=head_repo,
                pull_request=pull_request)
            resp = evaluator.eval()
    return resp, should_gen


def handle_results(eval_data: Box, results: Box, status: str):
    """
    Handles results POSTS from problem evaluators at the
    """
    # Get the eval_data using the result.eval_key

    results.username = eval_data.username
    results.botname = eval_data.botname
    results.problem_id = eval_data.problem_id
    results.status = status
    results.started = eval_data.started
    results.received = time.time()
    results.json_commit = eval_data.json_commit
    results.seed = eval_data.seed


    # TODO: Test locally generated results.json by transforming it to required
    #   format - pull eval info from KV store using eval_key
    #   Add:
    #   - username
    #   - botname
    #   - problem
    #   - "status": "success",
    #   - "utc_timestamp": 86600000,
    #   - "json_commit": "https://github.com/deepdrive/agent-zoo/commit/3a0e6af15c5ee05b62c6705d40aece250112a57d"
    #   - "source_commit": "https://github.com/crizCraig/forward-agent/commit/defc93d95944099d3e61cda6542bb4ffe7a28abf"
    #   -

    pass