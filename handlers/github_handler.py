from botleague_helpers.crypto import decrypt_symmetric
from pyramid.view import view_config, view_defaults

from constants import ON_GAE
from handlers.pr_handler import handle_pr_request
from pyramid import httpexceptions
from logs import log

from botleague_helpers.config import blconfig

from utils import get_liaison_db_store


@view_defaults(route_name='github_payload',
               renderer='json',
               request_method='POST')
class PayloadView(object):
    """
    View receiving of Github payload. By default, this view it's fired only if
    the request is json and method POST.
    """

    def __init__(self, request):
        self.request = request
        self.check_gae_enabled()

        if not blconfig.is_test:
            self.check_hmac()

        # Payload from Github, it's a dict
        self.payload = self.request.json

    @staticmethod
    def check_gae_enabled():
        db = get_liaison_db_store()
        if ON_GAE and db.get('DISABLE_GIT_HOOK_CONSUMPTION') is True:
            raise httpexceptions.HTTPLocked('Git hooks disabled')

    def check_hmac(self):
        hmac_sig = self.request.headers.get('X-Hub-Signature')
        if not hmac_sig:
            raise httpexceptions.HTTPForbidden('No X-Hub-Signature found')
        import hmac
        import hashlib
        db = get_liaison_db_store()
        shared_secret = decrypt_symmetric(db.get(
            'BL_GITHUB_WEBOOK_SECRET_encrypted'))
        shared_secret = bytes(shared_secret, 'utf-8')
        hmac_gen = hmac.new(shared_secret, digestmod=hashlib.sha1)
        hmac_gen.update(self.request.body)
        hmac_sig_check = hmac_gen.hexdigest()
        hmac_sig = hmac_sig[5:]
        if hmac_sig != hmac_sig_check:
            raise httpexceptions.HTTPForbidden(
                'Webhook HMAC in X-Hub-Signature does not match. Check secret'
                ' key in webhook matches BL_GITHUB_WEBOOK_SECRET in Firestore')

    @view_config(header='X-Github-Event:push')
    def payload_push(self):
        """This method is a continuation of PayloadView process, triggered if
        header HTTP-X-Github-Event type is Push"""
        # {u'name': u'marioidival', u'email': u'marioidival@gmail.com'}
        print(self.payload['pusher'])

        # TODO: Set should gen when a problem readme changes

        # do busy work...
        return 'nothing to push payload'  # or simple {}

    @log.catch(reraise=True)
    @view_config(header='X-Github-Event:pull_request')
    def payload_pull_request(self):
        """This method is a continuation of PayloadView process, triggered if
        header HTTP-X-Github-Event type is Pull Request"""
        # {u'name': u'marioidival', u'email': u'marioidival@gmail.com'}
        handle_pr_request(self.payload)

        # Responses are sent via creating statuses on the pull request:
        #   c.f. create_status

        return 'Successfully processed pull request'  # or simple {}

    @view_config(header='X-Github-Event:ping')
    def payload_push_ping(self):
        """This method is responding to a webhook ping"""
        return {'ping': True}
