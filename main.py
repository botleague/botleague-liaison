from __future__ import print_function

import os
from wsgiref.simple_server import make_server
from pyramid.config import Configurator
from pyramid.view import view_config, view_defaults
from pyramid.response import Response
import github
from github import Github, NamedUser


TOKEN_NAME = 'CI_HOOKS_GITHUB_TOKEN'
if 'IS_APP_ENGINE' not in os.environ:
    if TOKEN_NAME not in os.environ:
        raise RuntimeError('No github token in env')
    GITHUB_TOKEN = os.environ[TOKEN_NAME]
else:
    import firebase_admin
    from firebase_admin import firestore
    firebase_admin.initialize_app()
    SECRETS = firestore.client().collection('secrets')
    GITHUB_TOKEN = SECRETS.document(TOKEN_NAME).get().to_dict()['token']


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
            github_client = Github(GITHUB_TOKEN)

            commit_sha = self.payload['pull_request']['head']['sha']
            repo_name = self.payload['pull_request']['base']['repo']['full_name']

            status = create_status(commit_sha, github_client, repo_name)

        # do busy work...
        return "nothing to pull request payload"  # or simple {}

    @view_config(header="X-Github-Event:ping")
    def payload_push_ping(self):
        """This method is responding to a webhook ping"""
        return {'ping': True}


def check_token(request):
    if GITHUB_TOKEN:
        return Response('I have a token of length %r that starts '
                        'with %s' % (len(GITHUB_TOKEN), GITHUB_TOKEN[:4]))
    else:
        return Response('Not token found')


def root(request):
    return Response('yo')


def adhoc():



    repo_name = 'deepdrive/agent-zoo'
    commit_sha = 'ff075f40afe1e2545ee6cb8e029dc78c83b9f740'

    github_client = Github(GITHUB_TOKEN)

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
    config.add_route(name='check_token', pattern='/check_token')

    config.add_view(view=root, route_name='root')
    config.add_view(view=check_token, route_name='check_token')

    config.add_route(name="github_payload", pattern="/github_payload")
    # The view for the Github payload route is added via class annotation

    config.scan()
    app = config.make_wsgi_app()


if __name__ == "__main__":
    server = make_server("0.0.0.0", 8888, app)
    server.serve_forever()
