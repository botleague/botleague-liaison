from __future__ import print_function

import os
from wsgiref.simple_server import make_server
from pyramid.config import Configurator
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

        # do busy work...
        return "nothing to push payload"  # or simple {}

    @view_config(header="X-Github-Event:pull_request")
    def payload_pull_request(self):
        """This method is a continuation of PayloadView process, triggered if
        header HTTP-X-Github-Event type is Pull Request"""
        # {u'name': u'marioidival', u'email': u'marioidival@gmail.com'}
        action = self.payload['action']
        if action == 'open':
            print(self.payload['pusher'])
            github_client = Github(c.GITHUB_TOKEN)

            commit_sha = self.payload['pull_request']['head']['sha']
            repo_name = self.payload['pull_request']['base']['repo']['full_name']

            # TODO: Validate bot.json

            # TODO: Validate that user name matches agent_source_commit
            #   and agent_json_commit.

            status = create_status(commit_sha, github_client, repo_name)

        # do busy work...
        return "nothing to pull request payload"  # or simple {}

    @view_config(header="X-Github-Event:ping")
    def payload_push_ping(self):
        """This method is responding to a webhook ping"""
        return {'ping': True}


def diagnostics(request):
    if c.GITHUB_TOKEN:
        return Response('I have a github token of length %r that starts '
                        'with %s' % (len(c.GITHUB_TOKEN), c.GITHUB_TOKEN[:4]))
    else:
        return Response('Not token found')


def root(request):
    return Response('yo')


def adhoc():
    repo_name = 'deepdrive/agent-zoo'
    commit_sha = 'ff075f40afe1e2545ee6cb8e029dc78c83b9f740'

    github_client = Github(c.GITHUB_TOKEN)

    github.enable_console_debug_logging()


    # org = github_client.get_organization('deepdrive')
    #
    # user_org = github_client.get_user('deepdrive')

    status = create_status(commit_sha, github_client, repo_name)

    print(status)
    # Then play with your Github objects:
    # for repo in github_client.get_user().get_repos():
    #     print(repo.name)


def create_status(commit_sha, github_client, repo_name):
    repo = github_client.get_repo(repo_name)
    commit = repo.get_commit(sha=commit_sha)
    # error, failure, pending, or success
    status = commit.create_status(
        'pending',
        description='Agent!! is being evaluated against sim v3.0',
        target_url='https://deepdrive.io/leaderboards/this-agent/this-evaluation',
        context='Deepdrive')
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
