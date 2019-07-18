from __future__ import print_function

from wsgiref.simple_server import make_server

from botleague_helpers.config import blconfig

from handlers.confirm_handler import handle_confirm_request

from pyramid.config import Configurator

from pyramid.response import Response
import github
from github import Github

from handlers.results_handler import handle_results_request


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
    return Response('Botleague liaison service<br>https://github.com/botleague/botleague-liaison<br>https://drive.google.com/file/d/1Zqa9ykc4w6yrOVSdmQCPkxUMbUPjQQRg/view')


def adhoc():
    repo_name = 'botleague/botleague'
    commit_sha = 'ff075f40afe1e2545ee6cb8e029dc78c83b9f740'

    github_client = Github(blconfig.github_token)

    github.enable_console_debug_logging()


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
