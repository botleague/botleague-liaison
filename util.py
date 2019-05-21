import constants as c


def get_from_github(client, filename):
    relative_path = 'problems/{id}/{filename}'.format(id=self.id,
                                                      filename=filename)
    try:
        contents = github.get_contents(relative_path)
        content_str = contents.decoded_content.decode('utf-8')
    except UnknownObjectException:
        log.error('Unable to find %s in %s', relative_path, github.html_url)
        content_str = ''
    ret = content_str
    return ret