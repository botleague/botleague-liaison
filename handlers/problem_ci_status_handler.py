from typing import Tuple

from box import Box

from problem_ci import get_problem_ci_db_id
from responses.error import Error
from utils import get_liaison_db_store, dbox


def handle_problem_ci_status_request(request) -> Tuple[Box, Error]:
    if 'id' in request.params:
        problem_ci_id = request.params['id']
    else:
        data = Box(request.json)
        commit = data.commit
        pr_number = data.pr_number
        problem_ci_id = get_problem_ci_db_id(pr_number, commit)
    db = get_liaison_db_store()
    error = Error()
    problem_ci = dbox(db.get(problem_ci_id))
    body = Box(status=problem_ci.status or 'not-found',
               created_at=str(problem_ci.created_at),
               results_gists=problem_ci.gists or [])
    return body, error

