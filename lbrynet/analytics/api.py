import functools
import json
import logging

from requests import auth
from requests_futures import sessions

from lbrynet import conf
from lbrynet.analytics import utils


log = logging.getLogger(__name__)


def log_response(fn):
    def _log(future):
        if future.cancelled():
            log.warning('Request was unexpectedly cancelled')
        elif future.exception():
            exc, traceback = future.exception_info()
            log.warning('Failed to send an analytics event', exc_info=(type(exc), exc, traceback))
        # GRIN TURNED THIS OFF. Segment only has one response: {"success": true}
        # else:
        #     response = future.result()
        #     log.debug('Response (%s): %s', response.status_code, response.content)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        future = fn(*args, **kwargs)
        future.add_done_callback(_log)
        return future
    return wrapper


class Api(object):
    def __init__(self, session, url, write_key):
        self.session = session
        self.url = url
        self.write_key = write_key

    def post(self, endpoint, data):
        # there is an issue with a timing condition with keep-alive
        # that is best explained here: https://github.com/mikem23/keepalive-race
        #
        #   If you make a request, wait just the right amount of time,
        #   then make another request, the requests module may opt to
        #   reuse the connection, but by the time the server gets it the
        #   timeout will have expired.
        #
        # by forcing the connection to close, we will disable the keep-alive.
        assert endpoint[0] == '/'
        headers = {"Connection": "close"}
        return self.session.post(
            self.url + endpoint, json=data, auth=self.auth, headers=headers)

    @property
    def auth(self):
        return auth.HTTPBasicAuth(self.write_key, '')

    @log_response
    def batch(self, events):
        """Send multiple events in one request.

        Each event needs to have its type specified.
        """
        data = json.dumps({
            'batch': events,
            'sentAt': utils.now(),
        })
        log.debug('sending %s events', len(events))
        log.debug('Data: %s', data)
        return self.post('/batch', data)

    @log_response
    def track(self, event):
        """Send a single tracking event"""
        log.debug('Sending track event: %s', event)
        return self.post('/track', event)

    @classmethod
    def new_instance(cls, session=None):
        """Initialize an instance using values from the configuration"""
        if not session:
            session = sessions.FuturesSession()
        return cls(
            session,
            conf.settings['ANALYTICS_ENDPOINT'],
            utils.deobfuscate(conf.settings['ANALYTICS_TOKEN'])
        )
