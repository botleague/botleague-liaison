from __future__ import print_function

import os
from wsgiref.simple_server import make_server

from bot_eval import BotEval
from botleague_helpers.constants import GITHUB_TOKEN, SHOULD_GEN_KEY
from botleague_helpers.key_value_store import SimpleKeyValueStore
from responses import ErrorResponse, StartedResponse, RegenResponse, \
    IgnoreResponse
from pyramid.config import Configurator
from pyramid.httpexceptions import HTTPClientError
from pyramid.view import view_config, view_defaults
from pyramid.response import Response
import github
from github import Github, NamedUser
import constants as c
import key_value_store  # Do this after firebase is initialized


@view_defaults(
    route_name="github_payload", renderer="json", request_method="POST"
)
class PayloadView(object):
    """
    View receiving of Github payload. By default, this view it's fired only if
    the request is json and method POST.
    """

    def __init__(self, request):
        self.request = request
        # Payload from Github, it's a dict
        self.payload = self.request.json

    @view_config(header="X-Github-Event:push")
    def payload_push(self):
        """This method is a continuation of PayloadView process, triggered if
        header HTTP-X-Github-Event type is Push"""
        # {u'name': u'marioidival', u'email': u'marioidival@gmail.com'}
        print(self.payload['pusher'])

        # TODO: Set should gen when a problem readme changes

        # do busy work...
        return "nothing to push payload"  # or simple {}

    @view_config(header="X-Github-Event:pull_request")
    def payload_pull_request(self):
        """This method is a continuation of PayloadView process, triggered if
        header HTTP-X-Github-Event type is Pull Request"""
        # {u'name': u'marioidival', u'email': u'marioidival@gmail.com'}
        action = self.payload['action']
        if action in ['opened', 'synchronize', 'reopened']:
            self.process_pull_request_changes()

        # do busy work...
        return "nothing to pull request payload"  # or simple {}

    def process_pull_request_changes(self):
        pull_request = self.payload['pull_request']
        head = pull_request['head']
        head_repo_name = head['repo']['full_name']
        head_repo = c.GITHUB_CLIENT.get_repo(head_repo_name)
        base_repo_name = pull_request['base']['repo']['full_name']
        base_repo = c.GITHUB_CLIENT.get_repo(base_repo_name)
        pull_number = pull_request['number']

        # Get all the changed files in pull request
        changed_files = list(base_repo.get_pull(pull_number).get_files())

        (base_dirs,
         botname_dirs,
         changed_filenames,
         changed_filetypes,
         user_dirs,
         err) = self.group_changed_files(changed_files)

        should_gen = False
        if err is not None:
            ret_status = c.CI_STATUS_ERROR
            resp = err
        elif base_dirs == [c.BOTS_DIR]:
            # TODO: Verify that botnames and usernames have not been changed
            #   We do this to avoid complicated migrations in the leaderboard
            #   data. If someone changes their GitHub name, they will get a new
            #   user for now.
            resp, should_gen = self.process_changed_bot(
                base_repo, botname_dirs, changed_filenames, head_repo,
                pull_request, user_dirs, changed_filetypes)
        elif base_dirs == [c.PROBLEMS_DIR]:
            # Trigger problem CI
            # TODO: Verify that a problem submission does not change the name of an existing problem.
            pass
        elif c.BOTS_DIR in base_dirs or c.PROBLEMS_DIR in base_dirs:
            # Fail pull request, say that only bots or problems can be changed
            pass
        elif 'json' in changed_filetypes:
            # Fail pull request. Unexpected files, json files should
            # only be changed in the context of a bot or problem.
            pass
        else:
            # Allow the pull request, likely a docs / license, etc... change
            resp = IgnoreResponse('No leaderboard changes detected')
        commit_sha = self.payload['pull_request']['head']['sha']

        if isinstance(resp, ErrorResponse):
            ret_status = c.CI_STATUS_ERROR
        elif isinstance(resp, StartedResponse):
            ret_status = c.CI_STATUS_PENDING
        elif isinstance(resp, RegenResponse):
            ret_status = c.CI_STATUS_SUCCESS
        else:
            ret_status = c.CI_STATUS_SUCCESS

        if should_gen:
            SimpleKeyValueStore().set(SHOULD_GEN_KEY, True)

        status = create_status(ret_status, resp.msg,
                               commit_sha, c.GITHUB_CLIENT, base_repo_name, )

    @staticmethod
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
            if base_dir == c.BOTS_DIR:
                if len(path_parts) != 4:
                    # Expect something like
                    #   ['bots', username, botname, 'bot.json']
                    err = ErrorResponse('Malformed bot submission')
                    break
                elif path_parts[-1] not in c.ALLOWED_BOT_FILENAMES:
                    err = ErrorResponse('%s not an allowed bot file name' %
                                        path_parts[-1])
                    break
                elif changed_file.status == 'renamed':
                    err = ErrorResponse('Renaming bots currently not supported')
                    break
                else:
                    user_dirs.add(path_parts[1])
                    botname_dirs.add(path_parts[2])
            elif base_dir == c.PROBLEMS_DIR:
                if len(path_parts) != 3:
                    # Expect something like
                    #   ['problems', problem_id, 'problem.json']
                    err = ErrorResponse('Malformed problem submission')
                    break
                elif path_parts[-1] not in c.ALLOWED_PROBLEM_FILENAMES:
                    err = ErrorResponse('%s not an allowed bot file name' %
                                        path_parts[-1])
                    break
                elif changed_file.status == 'renamed':
                    err = ErrorResponse('Renaming problems currently '
                                        'not supported')
                    break
                else:
                    problem_dirs.add(path_parts[1])
            base_dirs.add(base_dir)
            filetype = filename.split('.')[-1]
            changed_filetypes.add(filetype)
        base_dirs = list(base_dirs)
        return (base_dirs, botname_dirs, changed_filenames,
                changed_filetypes, user_dirs, err)

    @staticmethod
    def process_changed_bot(base_repo, botname_dirs, changed_filenames,
                            head_repo, pull_request, user_dirs,
                            changed_filetypes):
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
                evaluator = BotEval(botname=botname,
                                    changed_filenames=changed_filenames,
                                    user_or_org=user_or_org,
                                    base_repo=base_repo, head_repo=head_repo,
                                    pull_request=pull_request)
                resp = evaluator.eval()
        return resp, should_gen

    @view_config(header="X-Github-Event:ping")
    def payload_push_ping(self):
        """This method is responding to a webhook ping"""
        return {'ping': True}


def diagnostics(request):
    if GITHUB_TOKEN:
        return Response('I have a github token of length %r that starts '
                        'with %s' % (len(GITHUB_TOKEN), GITHUB_TOKEN[:4]))
    else:
        return Response('Not token found')


def root(request):
    return Response('yo')


def adhoc():
    repo_name = 'botleague/botleague'
    commit_sha = 'ff075f40afe1e2545ee6cb8e029dc78c83b9f740'

    github_client = Github(GITHUB_TOKEN)

    github.enable_console_debug_logging()


    # org = github_client.get_organization('deepdrive')
    #
    # user_org = github_client.get_user('deepdrive')

    status = create_status('error', 'error msg', commit_sha, github_client,
                            repo_name)

    print(status)
    # Then play with your Github objects:
    # for repo in github_client.get_user().get_repos():
    #     print(repo.name)


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


# `app` needs to be global to work with App Engine
with Configurator() as config:

    config.add_route(name='root', pattern='/')
    config.add_view(view=root, route_name='root')

    config.add_route(name='diagnostics', pattern='/diagnostics')
    config.add_view(view=diagnostics, route_name='diagnostics')

    # TODO: Implement confirm request
    """
    ##### 2. Send `/confirm` POST
    
    Problem evaluators must then send a confirmation request with the `eval-key` to `https://liaison.botleague.io/confirm` to verify that botleague indeed initiated the evaluation. If we do not respond with a 200, you
    should abort the evaluation.
    """

        # TODO: Implement results request, and set should_gen_leaderboard to true
    """
    ##### 3. Send `results.json` POST
    
    Finally evaluators POST `results.json` to `https://liaison.botleague.io/results` with the `eval-key` to complete the evaluation and to be included on the Bot League leaderboards. An example `results.json` can be found [here](problems/examples/results.json).
    """

    config.add_route(name='github_payload', pattern='/github_payload')
    # The view for the Github payload route is added via class annotation

    config.scan()
    app = config.make_wsgi_app()


if __name__ == "__main__":
    server = make_server("0.0.0.0", 8888, app)
    server.serve_forever()
