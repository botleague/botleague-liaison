from glob import glob
from os.path import join
from typing import Union

import github
from botleague_helpers.reduce import create_reduce
from botleague_helpers.utils import box2json
from box import Box
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from logs import log

from bot_eval import get_bot_eval
from responses.pr_responses import RegenPrResponse, ErrorPrResponse, \
    ProblemCIResponse, NoBotsResponse, EvalStartedPrResponse, \
    EvalErrorPrResponse
from constants import BOTLEAGUE_REPO_ROOT, ONGOING_PROBLEM_CI_KEY_PREFIX
from utils import read_box, get_liaison_db_store


PROBLEM_CI_STATUS_PENDING = 'pending'
PROBLEM_CI_STATUS_FAILED = 'failed'
PROBLEM_CI_STATUS_PASSED = 'passed'


def process_changed_problem(changed_problem_definitions,
                            base_repo, changed_filenames,
                            changed_files, head_repo, pull_request,
                            user_dirs, changed_filetypes, from_mock,
                            github_client: github.Github,
                            botleague_liaison_host=None,
                            replace_sim_url=None):
    should_gen = False
    if not changed_problem_definitions:
        resp = RegenPrResponse(
            f'Generating leaderboard for problem change. PR '
            f'changed files were '
            f'{box2json(changed_files)}')
        should_gen = True
    elif len(changed_problem_definitions) > 1:
        # TODO: Nothing wrong with enabling this except for risk of
        #   evaling a ton of bots on accident
        resp = ErrorPrResponse('Can only change one problem at a time')
    else:
        prob_def = read_box(
            join(BOTLEAGUE_REPO_ROOT, changed_problem_definitions[0]))
        problem_id = '/'.join(changed_problem_definitions[0].split('/')[-3:-1])
        # For each bot that lists this problem, run an eval and collect the
        # results.
        bots_with_problem = Box()
        for f_name in glob(f'{BOTLEAGUE_REPO_ROOT}/bots/*/*/bot.json'):
            bot = read_box(f_name)
            botname = f_name.split('/')[-2]
            bot_user = f_name.split('/')[-3]
            if problem_id in bot.problems:
                bots_with_problem[(bot_user, botname)] = bot
        if not bots_with_problem:
            resp = NoBotsResponse('No bots with this problem, nothing to eval')
        else:
            resp = eval_bots(base_repo, bots_with_problem, changed_filenames,
                             changed_files, from_mock, github_client, head_repo,
                             prob_def, problem_id, pull_request,
                             botleague_liaison_host, replace_sim_url)
            if isinstance(resp, ProblemCIResponse):
                pci_id = get_problem_ci_db_id(
                    pull_number=pull_request.number,
                    pull_head_commit=pull_request.head.sha[:6])
                problem_ci = Box(
                    id=pci_id,
                    pull_request=pull_request,
                    bot_eval_keys=[b.eval_key for b in resp.bot_evals],
                    prob_def=prob_def,
                    botleague_liaison_host=botleague_liaison_host,
                    created_at=SERVER_TIMESTAMP,
                    status=PROBLEM_CI_STATUS_PENDING,)
                db = get_liaison_db_store()
                db.set(pci_id, problem_ci)
                log.success(f'Started problem ci: {pci_id}')

    return resp, should_gen


def get_problem_ci_db_id(pull_number, pull_head_commit):
    ret = f'{ONGOING_PROBLEM_CI_KEY_PREFIX}_' \
          f'PR:{pull_number}-' \
          f'sha:{pull_head_commit[:6]}'
    return ret


def eval_bots(base_repo, bots_with_problem, changed_filenames, changed_files,
              from_mock, github_client, head_repo, prob_def, problem_id,
              pull_request, botleague_liaison_host, replace_sim_url) \
        -> Union[ProblemCIResponse, EvalErrorPrResponse]:
    bot_evals = []

    # Create the reduce record that we will use to fan in results with
    create_reduce(get_problem_ci_db_id(
                    pull_number=pull_request.number,
                    pull_head_commit=pull_request.head.sha[:6]))

    for (bot_user, botname), bot in bots_with_problem.items():
        bot_eval = get_bot_eval(use_mock=from_mock)(
            botname=botname,
            changed_filenames=changed_filenames,
            changed_files=changed_files,
            user_or_org_dir=bot_user,
            base_repo=base_repo,
            head_repo=head_repo,
            pull_request=pull_request,
            github_client=github_client,
            botleague_liaison_host=botleague_liaison_host)
        trigger_resp = bot_eval.trigger_single_eval(
            bot_def=bot, problem_def=prob_def, problem_id=problem_id,
            problem_ci_replace_sim_url=replace_sim_url)
        if isinstance(trigger_resp, EvalStartedPrResponse):
            eval_data = trigger_resp.eval_data
            bot_evals.append(eval_data)
            log.success(f'Triggered '
                        f'{box2json(eval_data)}')
        elif isinstance(trigger_resp, EvalErrorPrResponse):
            log.error(f'Could not evaluate bot {bot_user}:{botname}. '
                      f'Error: {trigger_resp.msg}')
            return trigger_resp
    ci_message = f'Triggered {len(bot_evals)} evals'
    resp = ProblemCIResponse(ci_message, bot_evals)
    log.success(ci_message)
    return resp
