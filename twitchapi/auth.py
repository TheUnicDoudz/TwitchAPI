import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from http import HTTPStatus
import threading
import urllib.parse
import logging
import secrets
from random import randint

import requests

DEFAULT_ADDRESS = "0.0.0.0"
DEFAULT_PORT = 8000
REDIRECT_URI = f"http://localhost:{DEFAULT_PORT}/oauth2callback"
DEFAULT_TIMEOUT = 600

access_token_dict = {}


class WebRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        logging.info(f'client:  {self.client_address}')
        logging.info(f'command: {self.command}')
        logging.info(f'path:    {self.path}')

        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)

        if url.path == "/oauth2callback":
            logging.info('callback!')
            logging.info(query)
            if 'state' in query and 'code' in query:
                state = query['state'][0]
                code = query['code'][0]
                access_token_dict[state] = code
            else:
                logging.error("No state provided")

        self.send_response(HTTPStatus.OK)

    def do_POST(self):
        return self.do_GET()


class UriServer():

    def __init__(self,
                 address=DEFAULT_ADDRESS,
                 port=DEFAULT_PORT,
                 start=False):

        self.address = address
        self.port = port

        if start is True:
            self.start()

    def __http_thread(self):
        self.server = HTTPServer(('', self.port), WebRequestHandler)
        logging.info(f'Serving on {self.server.server_address}')

        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            pass
        logging.info('Exiting HTTP thread')

    def start(self):
        self.thread = threading.Thread(target=self.__http_thread)
        self.thread.start()

    def stop(self):

        logging.info('Stopping server')
        self.server.shutdown()

        logging.info('Join thread')
        self.thread.join()
        self.server.server_close()
        logging.info('Server stopped!')

    def get_access_token(self, state: str) -> str:

        access_token = None

        if state in access_token_dict:
            access_token = access_token_dict[state]
            access_token_dict.pop(state)  # Prevent replay attack

        return access_token

    def refresh_access_token(self, cliend_id: str, scope: list[str],
                     redirect_uri: str = REDIRECT_URI,
                     timeout: int = DEFAULT_TIMEOUT) -> str | None:

        access_token = None
        twitchid_url = "https://id.twitch.tv/oauth2/authorize"

        state_length = randint(16, 32)
        state = secrets.token_urlsafe(state_length)
        auth_params = {
            "client_id": cliend_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scope),
            "state": state
        }

        auth_params_str = urllib.parse.urlencode(auth_params)
        logging.debug(auth_params_str)

        r = requests.get(f"{twitchid_url}?{auth_params_str}")

        if r.status_code != 200:
            logging.error(r.content)
            return

        logging.debug("Authentification URL: " + r.url)
        webbrowser.open_new(r.url)

        logging.info("Retrieving access_token from redirect_uri..")

        self.start()

        start = time.time()

        try:
            while time.time() - start < timeout:
                access_token = uri.get_access_token(state)
                if access_token is not None:
                    logging.info('access_token received!')
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

        if access_token is None:
            logging.error("access_token not recovered..")
            return

        return access_token


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s.%(msecs)03d <%(levelname).1s> %(message)s',
                        datefmt='%y-%m-%d %H:%M:%S')
    logging.info("httpd URI Server")

    uri = UriServer()

    access_token = uri.refresh_access_token("zbbxen0gpgra4z35smahbajyi0o8o5", scope=["chat:read", "chat:edit"])

    logging.info(f"access_token: {access_token}")
