import random
import time
from typing import List, Union, Tuple

from box import Box, BoxList

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
    user_or_org_dir: str
    base_repo: Repository
    head_repo: Repository
    pr_event: Box
    seed: int
    github_client: github.Github

    def __init__(self, botname, changed_filenames, user_or_org_dir, base_repo,
                 head_repo, pull_request, github_client):
        super().__init__()  # Support multiple inheritance
        self.botname = botname
        self.changed_filenames: List[str] = changed_filenames
        self.user_or_org_dir = user_or_org_dir
        self.base_repo = base_repo
        self.head_repo = head_repo
        self.pr_event = pull_request
        self.league_commit_user = self.pr_event.user.login.lower()
        self.seed = random.choice(range(1, 10 ** 6))
        self.github_client = github_client

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
            # Yes, this is handled already in processed_changed_bots, so
            # it's redundant.
            ret = IgnoreResponse('Just a readme change, ignoring')
        else:
            ret = ErrorResponse('Unsupported bot files changed %r' %
                                self.changed_filenames)
        return ret

        # TODO: Copy the docker image over to GCR
        # TODO: Handle cases where only readme changes

    def eval_bot(self, bot_def_filename) -> Union[Response, List[Response]]:
        bot_def = self.github_get(self.head_repo, bot_def_filename)
        bot_def.source_commit = bot_def.get('source_commit', '')

        if self.user_or_org_dir != self.league_commit_user:
            if not self.user_in_org(user=self.league_commit_user,
                                    org=self.user_or_org_dir):
                return ErrorResponse('Bot directory does not match user or '
                                     'org name on source repo, aborting')
        problem_ids = bot_def.problems
        prob_responses = self.eval_bots_problems(problem_ids, bot_def)
        return prob_responses

    def eval_bots_problems(self, problem_ids, bot_def) -> List[Response]:
        responses:List[Response] = []
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
                        username=self.user_or_org_dir,
                        status=constants.EVAL_STATUS_STARTED,
                        started=now,
                        source_commit=bot_def.source_commit,
                        league_commit_sha=head_commit,
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

    @staticmethod
    def user_in_members(user, members):
        ret = any(m['login'].lower() == user.lower() for m in members)
        return ret

    def github_get(self, repo, filename):
        raise NotImplementedError()

    def user_in_org(self, user, org):
        raise NotImplementedError()


class BotEval(BotEvalBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def github_get(self, repo, filename):
        from utils import get_file_from_github
        return get_file_from_github(repo, filename)

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

    def user_in_org(self, user, org):
        public_members = list(self.github_client.get_organization('deepdrive')
                              .get_public_members())
        ret = user in public_members
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
        if eval_data.eval_key == eval_data.eval_id:
            raise RuntimeWarning('eval_key and eval_id should be different! '
                                 'The key is private, but the id can be '
                                 'public.')
        return EvalStartedResponse('Mock eval - nothing happening.', eval_data)

    def user_in_org(self, user, org):
        members = BoxList.from_json(filename=self.get_test_filename(
            'github_org_{org}_public_members.json').format(org=org))
        # TODO: We should also be checking that the user has commit or some higher
        #   level access than just member. i.e. EpicGames members should
        #   not be creating EpicGames problems.
        ret = self.user_in_members(user, members)
        return ret


def get_bot_eval(use_mock):
    if use_mock or blconfig.is_test or get_test_name_from_callstack():
        # Redundant guard rails
        return BotEvalMock
    else:
        return BotEval


def process_changed_bot(
        base_repo, botname_dirs, changed_filenames, head_repo, pull_request,
        user_dirs, changed_filetypes, from_mock,
        github_client:github.Github) -> \
        Tuple[Union[Response, List[Response]], bool]:
    should_gen = False
    user_dirs = list(user_dirs)
    if len(user_dirs) > 1:
        resp = ErrorResponse(
            'Can only submit bots for one user at a time')
    elif len(botname_dirs) > 1:
        resp = ErrorResponse('Can only submit one bot at a time')
    else:
        user_or_org_dir = user_dirs[0]
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
                user_or_org_dir=user_or_org_dir,
                base_repo=base_repo, head_repo=head_repo,
                pull_request=pull_request,
                github_client=github_client)
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
    results.league_commit_sha = eval_data.league_commit_sha
    results.source_commit = eval_data.source_commit
    results.seed = eval_data.seed
