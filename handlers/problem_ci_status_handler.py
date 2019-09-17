from typing import Tuple

from box import Box

from problem_ci import get_problem_ci_db_id
from responses.error import Error
from utils import get_liaison_db_store


def handle_problem_ci_status_request(request) -> Tuple[Box, Error]:
    data = Box(request.json)
    commit = data.commit
    pr_number = data.pr_number
    db = get_liaison_db_store()
    error = Error()
    problem_ci_id = get_problem_ci_db_id(pr_number, commit)
    problem_ci = db.get(problem_ci_id)

    body = Box(status=problem_ci.status,
               created_at=str(problem_ci.created_at))
    return body, error

