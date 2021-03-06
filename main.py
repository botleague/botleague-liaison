from __future__ import print_function

import os
import time
from wsgiref.simple_server import make_server

from botleague_helpers.config import blconfig
from box import Box
from logs import log

from constants import ON_GAE
from handlers.confirm_handler import handle_confirm_request

from pyramid.config import Configurator

from pyramid.response import Response
import github
from github import Github

from handlers.problem_ci_status_handler import handle_problem_ci_status_request
from handlers.results_handler import handle_results_request
from handlers import github_handler

try:
  import googleclouddebugger
  googleclouddebugger.enable()
except ImportError:
  pass

# TODO(Challenges): Allow private docker and github repos that grant access to
#  special botleague user. Related: https://docs.google.com/document/d/1IOMMtfEVaPWFPg8pEqPOPbLO__bs9_SCmA8_GbfGBTU/edit#

def diagnostics(request):
    tok = blconfig.github_token
    if tok:
        return Response('I have a github token of length %r that starts '
                        'with %s<br>' % (len(tok), tok[:3]))
    else:
        return Response('Not token found')


def handle_results(request):
    final_results, error, gist = handle_results_request(request)
    resp_box = Box(results=final_results, error=error, gist=gist)
    resp = Response(json=resp_box.to_dict())
    if error:
        resp.status_code = error.http_status_code
        log.error(f'Error handling results {error} - results:'
                           f' {resp_box.to_json(indent=2)}')
    else:
        log.info(f'Results response {resp_box.to_json(indent=2)}')
    return resp


def handle_problem_ci_status(request):
    start = time.time()
    body, error = handle_problem_ci_status_request(request)
    resp = Response(json=body.to_dict())
    if error:
        resp.status_code = error.http_status_code
    log.info(f'Problem CI status request took {time.time() - start} seconds')
    return resp


def handle_test_error(request):
    log.error('Testing error handling')


def handle_confirm(request):
    start = time.time()
    body, error = handle_confirm_request(request)
    resp = Response(json=body.to_dict())
    if error:
        resp.status_code = error.http_status_code
    log.info(f'Confirm request took {time.time() - start} seconds')
    return resp


def handle_root(request):
    return Response(f'Botleague liaison service<br>'
                    f'https://github.com/botleague/botleague-liaison<br>')


def handle_adhoc():
    repo_name = 'botleague/botleague'
    commit_sha = 'ff075f40afe1e2545ee6cb8e029dc78c83b9f740'

    # github_client = Github(blconfig.github_token)
    #
    # github.enable_console_debug_logging()


    # org = github_client.get_organization('deepdrive')
    #
    # user_org = github_client.get_user('deepdrive')

    # status = create_status('error', 'error msg', commit_sha, github_client,
    #                         repo_name)
    #
    # print(status)
    # Then play with your Github objects:
    # for repo in github_client.get_user().get_repos():
    #     print(repo.name)


# `app` needs to be global to work in App Engine
with Configurator() as config:

    config.add_route(name='root', pattern='/')
    config.add_view(view=handle_root, route_name='root')

    config.add_route(name='diagnostics', pattern='/diagnostics')
    config.add_view(view=diagnostics, route_name='diagnostics')

    config.add_route(name='confirm', pattern='/confirm')
    config.add_view(view=handle_confirm, route_name='confirm', renderer='json',
                    request_method='POST')

    config.add_route(name='results', pattern='/results')
    config.add_view(view=handle_results, route_name='results', renderer='json',
                    request_method='POST')

    config.add_route(name='problem_ci_status', pattern='/problem_ci_status')
    config.add_view(view=handle_problem_ci_status,
                    route_name='problem_ci_status', renderer='json',
                    request_method=('GET', 'POST'))

    # config.add_route(name='test_error', pattern='/test_error')
    # config.add_view(view=handle_test_error,
    #                 route_name='test_error', renderer='json',
    #                 request_method=('GET', 'POST'))

    config.add_route(name='github_payload', pattern='/github_payload')
    # The view for the Github payload route is added via class annotation

    config.scan(github_handler)
    app = config.make_wsgi_app()

if ON_GAE or __name__ == '__main__':
    # Load github token into memory so that requests don't need to do this.
    _tok_ = blconfig.github_token

if __name__ == '__main__':
    # TODO: Standardize on Pyramid or Flask with problem-endpoint
    server = make_server("0.0.0.0", 8888, app)
    log.success('Serving http://0.0.0.0:8888')
    server.serve_forever()
