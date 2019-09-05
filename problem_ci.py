from glob import glob
from os.path import join

import github
from box import Box

from bot_eval import get_bot_eval
from responses.pr_responses import RegenPrResponse, ErrorPrResponse, \
    ProblemCIResponse, NoBotsResponse
from constants import BOTLEAGUE_REPO_ROOT
from utils import read_box


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
                bot_evals.append(trigger_resp.eval_data)
            resp = ProblemCIResponse(f'Triggered {len(bot_evals)} evals',
                                     bot_evals)

    return resp, should_gen
