from glob import glob
from os.path import join
from typing import Union

import github
from box import Box
from loguru import logger as log

from bot_eval import get_bot_eval
from responses.pr_responses import RegenPrResponse, ErrorPrResponse, \
    ProblemCIResponse, NoBotsResponse, EvalStartedPrResponse, \
    EvalErrorPrResponse
from constants import BOTLEAGUE_REPO_ROOT, ONGOING_PROBLEM_CI_KEY_PREFIX
from utils import read_box, get_liaison_db_store


def process_changed_problem(changed_problem_definitions,
                            base_repo, changed_filenames,
                            changed_files, head_repo, pull_request,
                            user_dirs, changed_filetypes, from_mock,
                            github_client: github.Github):
    should_gen = False
    if not changed_problem_definitions:
        resp = RegenPrResponse(
            f'Generating leaderboard for problem change. PR '
            f'changed files were '
            f'{changed_files.to_json(indent=2, default=str)}')
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
                             prob_def, problem_id, pull_request)
            if isinstance(resp, ProblemCIResponse):
                problem_ci = Box(
                    pull_request=pull_request,
                    bot_eval_keys=[b.eval_key for b in resp.bot_evals],
                    prob_def=prob_def,
                    local_debug=local_debug,
                    created_at=SERVER_TIMESTAMP)
                db = get_liaison_db_store()
                db_key = get_problem_ci_db_key(
                    pull_number=pull_request.number,
                    pull_head_commit=pull_request.head.sha[:6])
                db.set(db_key, problem_ci)
                log.success(f'Started problem ci: {db_key}')

    return resp, should_gen


def get_problem_ci_db_key(pull_number, pull_head_commit):
    ret = f'{ONGOING_PROBLEM_CI_KEY_PREFIX}_' \
          f'PR:{pull_number}-' \
          f'sha:{pull_head_commit[:6]}'
    return ret


def eval_bots(base_repo, bots_with_problem, changed_filenames, changed_files,
              from_mock, github_client, head_repo, prob_def, problem_id,
              pull_request) -> Union[ProblemCIResponse, EvalErrorPrResponse]:
    bot_evals = []
    for (bot_user, botname), bot in bots_with_problem.items():
        bot_eval = get_bot_eval(use_mock=from_mock)(
            botname=botname,
            changed_filenames=changed_filenames,
            changed_files=changed_files,
            user_or_org_dir=bot_user,
            base_repo=base_repo,
            head_repo=head_repo,
            pull_request=pull_request,
            github_client=github_client)
        trigger_resp = bot_eval.trigger_single_eval(
            bot_def=bot, problem_def=prob_def, problem_id=problem_id)
        if isinstance(trigger_resp, EvalStartedPrResponse):
            eval_data = trigger_resp.eval_data
            bot_evals.append(eval_data)
            log.success(f'Triggered '
                        f'{eval_data.to_json(indent=2, default=str)}')
        elif isinstance(trigger_resp, EvalErrorPrResponse):
            log.error(f'Could not evaluate bot {bot_user}:{botname}. '
                      f'Error: {trigger_resp.msg}')
            return trigger_resp
    ci_message = f'Triggered {len(bot_evals)} evals'
    resp = ProblemCIResponse(ci_message, bot_evals)
    log.success(ci_message)
    return resp
