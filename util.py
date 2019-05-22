import json

import constants as c

import logging as log

log.basicConfig(level=log.INFO)

from github import UnknownObjectException


def get_from_github(repo, filename):
    """@:param filename: relative path to file in repo"""
    try:
        contents = repo.get_contents(filename)
        content_str = contents.decoded_content.decode('utf-8')
    except UnknownObjectException:
        log.error('Unable to find %s in %s', filename, repo.html_url)
        content_str = ''
    if filename.endswith('.json') and content_str:
        ret = json.loads(content_str)
    else:
        ret = content_str
    return ret
