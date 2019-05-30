from os.path import join
from typing import List

import logging as log

import github.Repository
from box import Box

import util
from bot_eval import process_changed_bot
from botleague_helpers.config import c, get_test_name_from_callstack
from botleague_helpers.key_value_store import SimpleKeyValueStore
from responses import ErrorResponse, StartedResponse, RegenResponse, \
    IgnoreResponse
import constants
from tests.mockable import Mockable
from util import read_json

log.basicConfig(level=log.INFO)


class PrProcessorBase:
    base_repo: github.Repository = None
    head_repo: github.Repository = None
    pull_number: int = -1
    pr_event: Box
    _github_client: github.Github = None

    def __init__(self):
        super().__init__()  # Support multiple inheritance

    def process_changes(self):
        pull_request = self.pr_event.pull_request
        head = pull_request.head
        head_repo_name = head.repo.full_name
        self.head_repo = self.get_repo(head_repo_name)
        base_repo_name = pull_request.base.repo.full_name
        self.base_repo = self.get_repo(base_repo_name)
        self.pull_number = pull_request.number

        # Get all the changed files in a pull request
        changed_files = self.get_changed_files()

        (base_dirs,
         botname_dirs,
         changed_filenames,
         changed_filetypes,
         user_dirs,
         err) = group_changed_files(changed_files)

        should_gen = False
        if err is not None:
            ret_status = constants.CI_STATUS_ERROR
            resp = err
        elif base_dirs == [constants.BOTS_DIR]:
            resp, should_gen = process_changed_bot(
                self.base_repo, botname_dirs, changed_filenames, self.head_repo,
                pull_request, user_dirs, changed_filetypes)
        elif base_dirs == [constants.PROBLEMS_DIR]:
            # Trigger problem CI
            # TODO: Verify that a problem submission does not change the name of
            #  an existing problem - use "renamed" to key off of as we did with
            #  bots
            pass
        elif constants.BOTS_DIR in base_dirs or \
                constants.PROBLEMS_DIR in base_dirs:
            # Fail pull request, either a bot or problem,
            # not both can be changed in a single pull request
            resp = ErrorResponse(
                'Either a bot or problem, not both, can be changed '
                'in a single pull request')
        elif 'json' in changed_filetypes:
            # Fail pull request. Unexpected files, json files should
            # only be changed in the context of a bot or problem.
            resp = ErrorResponse('Unexpected files, json files should '
                                 'only be changed in the context of a bot or '
                                 'problem.')
        else:
            # Allow the pull request, likely a docs / license, etc... change
            resp = IgnoreResponse('No leaderboard changes detected')
        commit_sha = self.pr_event.pull_request.head.sha

        if isinstance(resp, ErrorResponse):
            ret_status = constants.CI_STATUS_ERROR
        elif isinstance(resp, StartedResponse):
            ret_status = constants.CI_STATUS_PENDING
        elif isinstance(resp, RegenResponse):
            ret_status = constants.CI_STATUS_SUCCESS
        else:
            ret_status = constants.CI_STATUS_SUCCESS

        if should_gen:
            SimpleKeyValueStore().set(c.should_gen_key, True)

        status = self.create_status(
            ret_status, resp.msg, commit_sha, self.github_client,
            base_repo_name)
        return resp

    @staticmethod
    def create_status(status, msg, commit_sha, github_client, repo_name):
        raise NotImplementedError()

    @staticmethod
    def get_repo(repo_name):
        raise NotImplementedError()

    def get_changed_files(self) -> List[Box]:
        raise NotImplementedError()

    @property
    def github_client(self):
        raise NotImplementedError()


class PrProcessor(PrProcessorBase):
    def __init__(self, pr):
        if get_test_name_from_callstack():
            raise RuntimeError('Should not be using this class in tests!')
        super().__init__()
        self.pr = pr

    def get_changed_files(self):
        ret = list(self.base_repo.get_pull(self.pull_number).get_files())
        ret = [Box(r.raw_data) for r in ret]
        if constants.SHOULD_RECORD:
            util.write_json(ret, join(constants.ROOT_DIR,
                                      'recorded-changed-files.json'))
        return ret

    def get_repo(self, repo_name):
        return self.github_client.get_repo(repo_name)

    @staticmethod
    def create_status(status, msg, commit_sha, github_client, repo_name):
        repo = github_client.get_repo(repo_name)
        commit = repo.get_commit(sha=commit_sha)
        # error, failure, pending, or success
        status = commit.create_status(
            status,
            description=msg,
            target_url='https://botleague.io/users/username/botname/this-evaluation',
            context='Botleague')
        return status

    @property
    def github_client(self):
        if PrProcessor._github_client is None:
            # Lazy load class variable. Note this doesn't affect the base class
            PrProcessor._github_client = github.Github(c.github_token)
        return PrProcessor._github_client


class PrProcessorMock(PrProcessorBase, Mockable):
    def __init__(self):
        super().__init__()
        self.pr_event = Box(read_json(self.get_test_filename('pr_event.json')))

    def get_changed_files(self):
        files = read_json(self.get_test_filename('changed-files.json'))
        ret = [Box(f) for f in files]
        return ret

    @staticmethod
    def get_repo(repo_name):
        return None

    @staticmethod
    def create_status(status, msg, commit_sha, github_client, repo_name):
        return None

    @property
    def github_client(self):
        return None


def get_pr_processor(pr_event=None) -> PrProcessorBase:
    if c.is_test:
        # This is a guard rail, you should just use the mock constructor in
        # tests
        ret = PrProcessorMock()
    else:
        ret = PrProcessor(pr_event)
    return ret


def group_changed_files(changed_files):
    base_dirs = set()
    user_dirs = set()
    botname_dirs = set()
    problem_dirs = set()
    changed_filenames = []
    changed_filetypes = set()
    err = None
    for changed_file in changed_files:
        filename = changed_file.filename
        changed_filenames.append(filename)
        path_parts = filename.split('/')
        base_dir = path_parts[0]
        err = None
        if base_dir == constants.BOTS_DIR:
            if len(path_parts) != 4:
                # Expect something like
                #   ['bots', username, botname, 'bot.json']
                err = ErrorResponse('Malformed bot submission')
                break
            elif path_parts[-1] not in constants.ALLOWED_BOT_FILENAMES:
                err = ErrorResponse('%s not an allowed bot file name' %
                                    path_parts[-1])
                break
            elif changed_file.status == 'renamed':
                # Verify that botnames and usernames have not been changed
                # We do this to avoid complicated migrations in the
                # leaderboard data. If someone changes their GitHub name,
                # they will get a new user for now.
                err = ErrorResponse('Renaming bots currently not supported')
                break
            else:
                user_dirs.add(path_parts[1])
                botname_dirs.add(path_parts[2])
        elif base_dir == constants.PROBLEMS_DIR:
            if len(path_parts) != 3:
                # Expect something like
                #   ['problems', problem_id, 'problem.json']
                err = ErrorResponse('Malformed problem submission')
                break
            elif path_parts[-1] not in constants.ALLOWED_PROBLEM_FILENAMES:
                err = ErrorResponse('%s not an allowed bot file name' %
                                    path_parts[-1])
                break
            elif changed_file.status == 'renamed':
                err = ErrorResponse(constants.RENAME_PROBLEM_ERROR_MSG)
                break
            else:
                problem_dirs.add(path_parts[1])
        base_dirs.add(base_dir)
        filetype = filename.split('.')[-1]
        changed_filetypes.add(filetype)
    base_dirs = list(base_dirs)
    return (base_dirs, botname_dirs, changed_filenames,
            changed_filetypes, user_dirs, err)
