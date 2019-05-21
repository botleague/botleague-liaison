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
    ret = content_str
    return ret
