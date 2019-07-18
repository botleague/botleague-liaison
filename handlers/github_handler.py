from box import Box
from leaderboard_generator.botleague_gcp.key_value_store import \
    get_key_value_store
from pyramid.view import view_config, view_defaults
from handlers.pr_handler import get_pr_processor
from pyramid import httpexceptions

from botleague_helpers.config import blconfig


@view_defaults(
    route_name='github_payload', renderer='json', request_method='POST'
)
class PayloadView(object):
    """
    View receiving of Github payload. By default, this view it's fired only if
    the request is json and method POST.
    """

    def __init__(self, request):
        self.request = request
        if not blconfig.is_test:
            self.check_hmac()

        # Payload from Github, it's a dict
        self.payload = self.request.json

    def check_hmac(self):
        hmac_sig = self.request.headers.get('X-Hub-Signature')
        if not hmac_sig:
            raise httpexceptions.HTTPForbidden('No X-Hub-Signature found')
        import hmac
        import hashlib
        kv = get_key_value_store()
        shared_secret = kv.get('BL_GITHUB_WEBOOK_SECRET')
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

    @view_config(header='X-Github-Event:pull_request')
    def payload_pull_request(self):
        """This method is a continuation of PayloadView process, triggered if
        header HTTP-X-Github-Event type is Pull Request"""
        # {u'name': u'marioidival', u'email': u'marioidival@gmail.com'}
        action = self.payload['action']
        if action in ['opened', 'synchronize', 'reopened']:
            pr_processor = get_pr_processor()
            pr_processor.pr_event = Box(self.payload)
            pr_processor.process_changes()

        # do busy work...
        return 'nothing to pull request payload'  # or simple {}

    @view_config(header='X-Github-Event:ping')
    def payload_push_ping(self):
        """This method is responding to a webhook ping"""
        return {'ping': True}