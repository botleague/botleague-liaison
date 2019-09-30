import json
import os
import random
import time
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from typing import List, Union, Tuple
from logs import log
from box import Box, BoxList

import constants
import github
import requests
from botleague_helpers.config import blconfig, get_test_name_from_callstack
from github import Repository
from responses.pr_responses import ErrorPrResponse, RegenPrResponse, \
    IgnorePrResponse, PrResponse, EvalErrorPrResponse, EvalStartedPrResponse
from tests.mockable import Mockable
from utils import read_file, get_str_or_box, get_liaison_db_store

from utils import generate_rand_alphanumeric


class BotEvalBase:
    botname: str
    changed_filenames: List[str]
    changed_files: List[Box]
    user_or_org_dir: str
    base_repo: Repository
    head_repo: Repository
    pr_event: Box
    seed: int
    github_client: github.Github
    botleague_liaison_host: str

    def __init__(self, botname, changed_filenames, changed_files,
                 user_or_org_dir, base_repo,
                 head_repo, pull_request, github_client,
                 botleague_liaison_host=None):
        super().__init__()  # Support multiple inheritance
        self.botname = botname
        self.changed_filenames: List[str] = changed_filenames
        self.changed_files: List[Box] = changed_files
        self.user_or_org_dir = user_or_org_dir
        self.base_repo = base_repo
        self.head_repo = head_repo
        self.pr_event = pull_request
        self.league_commit_user = self.pr_event.user.login.lower()
        self.seed = random.choice(range(1, 10 ** 6))
        self.github_client = github_client
        self.botleague_liaison_host = botleague_liaison_host or constants.HOST

    def eval(self) -> Union[PrResponse, List[PrResponse]]:
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
                ret = ErrorPrResponse('Only one bot per pull request allowed')
            else:
                bot_def_filename = bot_def_filenames[0]
                changed_ref = self.get_ref(bot_def_filename)
                ret = self.eval_bot(bot_def_filename, changed_ref)
        elif bot_readme_filenames:
            # Yes, this is handled already in processed_changed_bots, so
            # it's redundant.
            ret = IgnorePrResponse('Just a readme change, ignoring')
        else:
            ret = ErrorPrResponse('Unsupported bot files changed %r' %
                                  self.changed_filenames)
        return ret

        # TODO: Copy the bot image over to GCR

    def get_ref(self, bot_def_filename: str) -> str:
        for changed_file in self.changed_files:
            if changed_file.filename == bot_def_filename:
                bot_def_file = changed_file
                import urllib.parse as urlparse
                parsed = urlparse.urlparse(bot_def_file.contents_url)
                changed_ref = urlparse.parse_qs(parsed.query)['ref'][0]
                break
        else:
            raise RuntimeError('Could not find ref for changed file %s '
                               % bot_def_filename)
        return changed_ref

    def eval_bot(self, bot_def_filename: str,
                 bot_def_ref: str) -> Union[PrResponse, List[PrResponse]]:
        bot_def = self.github_get(self.head_repo, bot_def_filename,
                                  ref=bot_def_ref)
        if not bot_def:
            return ErrorPrResponse('Could not find bot.json')
        bot_def.source_commit = bot_def.get('source_commit', '')

        if self.user_or_org_dir != self.league_commit_user:
            if not self.user_in_org(user=self.league_commit_user,
                                    org=self.user_or_org_dir):
                return ErrorPrResponse('Bot directory does not match user or '
                                     'org name on source repo, aborting')
        problem_ids = bot_def.problems
        if len(problem_ids) != len(set(problem_ids)):
            return ErrorPrResponse('Duplicate problems detected')
        prob_responses = self.eval_bots_problems(problem_ids, bot_def)
        return prob_responses

    def eval_bots_problems(self, problem_ids, bot_def) -> List[PrResponse]:
        responses: List[PrResponse] = []
        for problem_id in problem_ids:
            problem_def_url = '%s/%s/%s' % (
                constants.PROBLEMS_DIR, problem_id,
                constants.PROBLEM_DEFINITION_FILENAME)

            # Ensure the problem exists
            # TODO: Use local repo clone for this instead
            problem_def = self.github_get(self.base_repo, problem_def_url)

            if not problem_def:
                # Problem does not exist
                responses.append(
                    EvalErrorPrResponse('Problem does not exist %s' %
                                        problem_id))
            else:
                # Trigger the eval at the problem endpoint
                resp = self.trigger_single_eval(bot_def, problem_def,
                                                problem_id)
                responses.append(resp)
        return responses

    def trigger_single_eval(self, bot_def, problem_def,
                            problem_id,
                            problem_ci_replace_sim_url=None) -> PrResponse:
        endpoint = problem_def.endpoint
        if problem_ci_replace_sim_url:
            problem_def.problem_ci_replace_sim_url = problem_ci_replace_sim_url
        eval_key = generate_rand_alphanumeric(25)
        eval_id = generate_rand_alphanumeric(25)
        eval_data = self.get_eval_data(eval_id, eval_key, problem_id, bot_def,
                                       problem_def)
        db = get_liaison_db_store()
        db_key = get_eval_db_key(eval_data.eval_key)
        db.set(db_key, eval_data)
        eval_data = db.get(db_key)  # Resolve timestamp
        resp = self.request_eval(endpoint, eval_data)
        return resp

    @staticmethod
    def request_eval(endpoint, eval_data) -> PrResponse:
        raise NotImplementedError()

    def get_eval_data(self, eval_id, eval_key, problem_id, bot_def,
                      problem_def) -> Box:
        # TODO: Move this to models/eval_data and use an object instead of a box
        pull_number = self.pr_event.number
        pull_url = self.pr_event.url
        pull_request_updated_at = self.pr_event.updated_at
        merge_commit_sha = self.pr_event.merge_commit_sha
        head_commit = self.pr_event.head.sha
        base_commit = self.pr_event.base.sha
        head_full_name = self.pr_event.head.repo.full_name
        base_full_name = self.pr_event.base.repo.full_name
        now = time.time()
        eval_data = Box(docker_tag=bot_def.docker_tag,
                        eval_key=eval_key,
                        eval_id=eval_id,
                        seed=self.seed,
                        problem_id=problem_id,
                        problem_def=problem_def,
                        botname=self.botname,
                        username=self.user_or_org_dir,
                        status=constants.EVAL_STATUS_STARTED,
                        started=now,
                        started_at=SERVER_TIMESTAMP,
                        source_commit=bot_def.source_commit,
                        league_commit_sha=head_commit,
                        botleague_liaison_host=self.botleague_liaison_host,
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

    def github_get(self, repo, filename, ref=None):
        raise NotImplementedError()

    def user_in_org(self, user, org):
        raise NotImplementedError()


class BotEval(BotEvalBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def github_get(self, repo, filename, ref=None):
        from utils import get_file_from_github
        return get_file_from_github(repo, filename, ref)

    @staticmethod
    def request_eval(endpoint: str, eval_data: Box) -> PrResponse:
        try:
            if 'REPLACE_PROBLEM_HOST' in os.environ:
                endpoint = os.environ['REPLACE_PROBLEM_HOST'] + \
                           endpoint[endpoint.find('/eval'):]
            # TODO: Don't pass everything through to endpoint - i.e. cleanse
            serializable_data = json.loads(eval_data.to_json(default=str))
            endpoint_resp = requests.post(endpoint,
                                          json=serializable_data,
                                          timeout=10)
        except requests.exceptions.Timeout:
            ret = EvalErrorPrResponse(
                'Endpoint %s took too long to respond' % endpoint)
        else:
            # Yay, we did not timeout!
            if endpoint_resp.status_code != 200:
                ret = EvalErrorPrResponse(
                    'Endpoint %s failed with HTTP %r, response body was %s'
                    % (endpoint, endpoint_resp.status_code,
                       endpoint_resp.content))
                log.error(ret.msg)
            else:
                ret = EvalStartedPrResponse('Started evaluation at %s' %
                                            endpoint, eval_data)
                # Now wait for a /confirm and /results request with the eval_key
        log.info(f'Request eval resp: {ret.msg}')
        return ret

    def user_in_org(self, user, org):
        try:
            public_members = list(self.github_client.get_organization(org)
                                  .get_public_members())
        except:
            log.exception(f'Unable to get users for {org}')
            return False

        # TODO: We should also be checking that the user has commit or some higher
        #   level access than just member. i.e. EpicGames members should
        #   not be creating EpicGames problems.
        public_members = [p.login.lower() for p in public_members]
        ret = user in public_members
        return ret


def get_eval_db_key(eval_key):
    # Prefix since we are going into our GCP app's global datastore
    return '%s_%s' % (constants.ONGOING_EVALUATIONS_KEY_PREFIX,
                      eval_key)


class BotEvalMock(BotEvalBase, Mockable):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def github_get(self, _repo, filename, ref=None):
        filepath = self.get_test_filename(filename)
        content_str = read_file(filepath)
        ret = get_str_or_box(content_str, filepath)
        return ret

    @staticmethod
    def request_eval(endpoint: str, eval_data: Box) -> PrResponse:
        if eval_data.eval_key == eval_data.eval_id:
            raise RuntimeWarning('eval_key and eval_id should be different! '
                                 'The key is private, but the id can be '
                                 'public.')
        return EvalStartedPrResponse('Mock eval - nothing happening.', eval_data)

    def user_in_org(self, user, org):
        members = BoxList.from_json(filename=self.get_test_filename(
            'github_org_{org}_public_members.json').format(org=org))
        ret = self.user_in_members(user, members)
        return ret


def get_bot_eval(use_mock):
    if use_mock or blconfig.is_test or get_test_name_from_callstack():
        # Redundant guard rails
        return BotEvalMock
    else:
        return BotEval


def process_changed_bot(
        base_repo, botname_dirs, changed_filenames,
        changed_files, head_repo, pull_request,
        user_dirs, changed_filetypes, from_mock,
        github_client: github.Github, botleague_liaison_host) -> \
        Tuple[Union[PrResponse, List[PrResponse]], bool]:
    should_gen_leaderboard = False
    user_dirs = list(user_dirs)
    if len(user_dirs) > 1:
        # TODO: Nothing wrong with enabling this except for risk of
        #   evaling a ton of bots on accident
        resp = ErrorPrResponse(
            'Can only submit bots for one user at a time')
    elif len(botname_dirs) > 1:
        resp = ErrorPrResponse('Can only submit one bot at a time')
    else:
        user_or_org_dir = user_dirs[0]
        botname = botname_dirs[0]
        if ['md'] == list(changed_filetypes):
            # Just a docs/readme change. Trigger leaderboard gen.
            should_gen_leaderboard = True
            resp = RegenPrResponse('Markdown only change detected, '
                                   'regenerating leaderboards')
        else:
            # Trigger bot evaluation
            evaluator = get_bot_eval(use_mock=from_mock)(
                botname=botname,
                changed_filenames=changed_filenames,
                changed_files=changed_files,
                user_or_org_dir=user_or_org_dir,
                base_repo=base_repo,
                head_repo=head_repo,
                pull_request=pull_request,
                github_client=github_client,
                botleague_liaison_host=botleague_liaison_host)
            resp = evaluator.eval()
    return resp, should_gen_leaderboard


