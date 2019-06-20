from __future__ import print_function

from wsgiref.simple_server import make_server
from pyramid import httpexceptions

from botleague_helpers.key_value_store import get_key_value_store
from box import Box

from botleague_helpers.config import blconfig

from pr_processor import get_pr_processor
from pyramid.config import Configurator
from pyramid.view import view_config, view_defaults
from pyramid.response import Response
import github
from github import Github

from pr_responses import ErrorPrResponse
from results_view import handle_results_request



@view_defaults(
    route_name='github_payload', renderer='json', request_method='POST'
)
class PayloadView(object):
    """
    View receiving of Github payload. By default, this view it's fired only if
    the request is json and method POST.
    """

    def __init__(self, request):
        self.request = request
        if not blconfig.is_test:
            self.check_hmac()

        # Payload from Github, it's a dict
        self.payload = self.request.json

    def check_hmac(self):
        hmac_sig = self.request.headers.get('X-Hub-Signature')
        if not hmac_sig:
            raise httpexceptions.HTTPForbidden('No X-Hub-Signature found')
        import hmac
        import hashlib
        kv = get_key_value_store()
        shared_secret = kv.get('BL_GITHUB_WEBOOK_SECRET')
        shared_secret = bytes(shared_secret, 'utf-8')
        hmac_gen = hmac.new(shared_secret, digestmod=hashlib.sha1)
        hmac_gen.update(self.request.body)
        hmac_sig_check = hmac_gen.hexdigest()
        hmac_sig = hmac_sig[5:]
        if hmac_sig != hmac_sig_check:
            raise httpexceptions.HTTPForbidden(
                'Webhook HMAC in X-Hub-Signature does not match. Check secret'
                ' key in webhook matches BL_GITHUB_WEBOOK_SECRET in Firestore')

    @view_config(header='X-Github-Event:push')
    def payload_push(self):
        """This method is a continuation of PayloadView process, triggered if
        header HTTP-X-Github-Event type is Push"""
        # {u'name': u'marioidival', u'email': u'marioidival@gmail.com'}
        print(self.payload['pusher'])

        # TODO: Set should gen when a problem readme changes

        # do busy work...
        return 'nothing to push payload'  # or simple {}

    @view_config(header='X-Github-Event:pull_request')
    def payload_pull_request(self):
        """This method is a continuation of PayloadView process, triggered if
        header HTTP-X-Github-Event type is Pull Request"""
        # {u'name': u'marioidival', u'email': u'marioidival@gmail.com'}
        action = self.payload['action']
        if action in ['opened', 'synchronize', 'reopened']:
            pr_processor = get_pr_processor()
            pr_processor.pr_event = Box(self.payload.raw_data)
            pr_processor.process_changes()

        # do busy work...
        return 'nothing to pull request payload'  # or simple {}

    @view_config(header='X-Github-Event:ping')
    def payload_push_ping(self):
        """This method is responding to a webhook ping"""
        return {'ping': True}


def diagnostics(request):
    tok = blconfig.github_token
    if tok:
        return Response('I have a github token of length %r that starts '
                        'with %s' % (len(tok), tok[:4]))
    else:
        return Response('Not token found')


def results(request):
    ret = handle_results_request(request).to_dict()
    return ret

def root(request):
    return Response('yo')


def adhoc():
    repo_name = 'botleague/botleague'
    commit_sha = 'ff075f40afe1e2545ee6cb8e029dc78c83b9f740'

    github_client = Github(blconfig.github_token)

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


# `app` needs to be global to work with App Engine
with Configurator() as config:

    config.add_route(name='root', pattern='/')
    config.add_view(view=root, route_name='root')

    config.add_route(name='diagnostics', pattern='/diagnostics')
    config.add_view(view=diagnostics, route_name='diagnostics')

    config.add_route(name='results', pattern='/results')
    config.add_view(view=results, route_name='results', renderer='json')

    # TODO: Implement confirm request
    """
    ##### 2. Send `/confirm` POST
    
    Problem evaluators must then send a confirmation request with the `eval-key` to `https://liaison.botleague.io/confirm` to verify that botleague indeed initiated the evaluation. If we do not respond with a 200, you
    should abort the evaluation.
    """

    # TODO: Route results POST request to handle_results, and set
    #  should_gen_leaderboard to true
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
