import time
import webbrowser
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from http import HTTPStatus
import threading
import urllib.parse
import logging
import secrets
from random import randint
import json
import os
import requests
from requests import Response

from twitchapi.exception import TwitchAuthorizationFailed, TwitchAuthentificationError, TwitchEndpointError
from twitchapi.twitchcom import TwitchEndpoint

DEFAULT_ADDRESS = "0.0.0.0"
DEFAULT_PORT = 8000
REDIRECT_URI_AUTH = f"http://localhost:{DEFAULT_PORT}/oauth2callback"
DEFAULT_TIMEOUT = 600
ACCESS_TOKEN_FILE = ".access_token"

code_dict = {}


class WebRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        logging.info(f'client:  {self.client_address}')
        logging.info(f'command: {self.command}')
        logging.info(f'path:    {self.path}')

        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)

        if url.path == "/oauth2callback":
            logging.info('Callback!')
            logging.debug(query)
            if 'state' in query and 'code' in query:
                logging.info("Code provided!")
                state = query['state'][0]
                code_dict[state] = query['code'][0]
            else:
                logging.error("No state provided")

        self.send_response(HTTPStatus.OK)

    def do_POST(self):
        return self.do_GET()


class AuthServer():

    def __init__(self,
                 address=DEFAULT_ADDRESS,
                 port=DEFAULT_PORT,
                 start=False):

        self.address = address
        self.port = port
        self._client_id = None
        self.__client_secret = None
        self.__credentials = None
        self.__headers = None

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

    def get_code(self, state: str) -> str:

        code = None

        if state in code_dict:
            code = code_dict[state]
            code_dict.pop(state)  # Prevent replay attack

        return code

    def get_access_token(self, client_id: str, client_secret: str, scope: list[str],
                         redirect_uri: str = REDIRECT_URI_AUTH,
                         timeout: int = DEFAULT_TIMEOUT) -> tuple[str, str, str]:

        access_token = None
        refresh_token = None
        expire_date = None
        code = None
        twitch_code_url = "https://id.twitch.tv/oauth2/authorize"
        twich_token_url = "https://id.twitch.tv/oauth2/token"

        state_length = randint(16, 32)
        state = secrets.token_urlsafe(state_length)
        code_auth_params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scope),
            "state": state
        }

        code_auth_params_str = urllib.parse.urlencode(code_auth_params)
        logging.debug(code_auth_params_str)

        r = requests.get(f"{twitch_code_url}?{code_auth_params_str}")

        if r.status_code != 200:
            logging.error(r.content)
            raise TwitchAuthorizationFailed("Failed to call the Authorization end point! Verify the Client ID of your "
                                            "application!")

        logging.debug("Authentification URL: " + r.url)
        webbrowser.open_new(r.url)

        logging.info("Retrieving access_token from redirect_uri..")

        self.start()

        start = time.time()

        try:
            while time.time() - start < timeout:
                code = self.get_code(state)
                if code is not None:
                    logging.info('access_token received!')
                    break
                time.sleep(1)

            if code is None:
                logging.error("code not recovered..")
                raise TwitchAuthorizationFailed("Fail to provide authorization code! Verify the redirect URI "
                                                "(if not default value)!")

            token_auth_params = {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri
            }

            token_auth_params_str = urllib.parse.urlencode(token_auth_params)

            logging.debug(token_auth_params_str)

            r = requests.post(f"{twich_token_url}?{token_auth_params_str}")

            if r.status_code != 200:
                logging.error(r.content)
                raise TwitchAuthorizationFailed("Fail to provide access token! Verify the Client secret of your "
                                                "application!")

            data = r.json()
            access_token = data["access_token"]
            refresh_token = data["refresh_token"]
            expire_date = (datetime.now() + timedelta(25)).strftime('%d/%m/%Y')
            logging.info('access_token received!')

        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

        logging.debug(f"OAuth token: {access_token}")
        logging.debug(f"Refresh token: {refresh_token}")
        return access_token, refresh_token, expire_date

    def refresh_token(self) -> None:

        twich_token_url = TwitchEndpoint.TWITCH_AUTH_URL

        token_auth_params = {
            "client_id": self._client_id,
            "client_secret": self.__client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.__credentials["refresh_token"]
        }

        token_auth_params_str = urllib.parse.urlencode(token_auth_params)

        r = requests.post(f"{twich_token_url}?{token_auth_params_str}")

        if r.status_code != 200:
            logging.error(r.content)
            raise TwitchAuthorizationFailed("Failed to call the Authorization end point! Verify the Client ID, the "
                                            "Client secret or the refresh token of your application!")
        data = r.json()
        access_token = data["access_token"]
        refresh_token = data["refresh_token"]
        expire_date = (datetime.now() + timedelta(25)).strftime('%d/%m/%Y')
        self.__credentials = {"access_token": access_token, "refresh_token": refresh_token, "expire_date": expire_date}
        with open(ACCESS_TOKEN_FILE, "w") as f:
            json.dump(self.__credentials, f)

        self.__headers = {
            "Authorization": f"Bearer {self.__credentials['access_token']}",
            "Client-Id": self._client_id,
            "Content-Type": "application/json"
        }

    def get_request(self, endpoint: str) -> dict:
        url_endpoint = TwitchEndpoint.TWITCH_ENDPOINT + endpoint
        r = self.__check_request(requests.get, url_endpoint)
        return r.json()

    def post_request(self, endpoint: str, data: dict) -> dict:
        url_endpoint = TwitchEndpoint.TWITCH_ENDPOINT + endpoint
        r = self.__check_request(requests.post, url_endpoint, data)
        return r.json()

    def __check_request(self, request_function, url_endpoint: str, data: dict = None) -> Response:
        params = {"url": url_endpoint, "headers": self.__headers}
        if data:
            params["json"] = data
        response = request_function(**params)
        if response.status_code >= 300:
            if response.status_code == 401:
                self.refresh_token()
                params["headers"] = self.__headers
                response = request_function(**params)
                if response.status_code != 200:
                    logging.error(response.content)
                    raise TwitchAuthentificationError("Something's wrong with the access token!!")
            else:
                logging.error(response.content)
                raise TwitchEndpointError(
                    f"The url {url_endpoint} is not correct or you don't have the rights to use it!")
        return response

    def authentication(self, client_id: str, client_secret: str, scope: list[str], timeout: int = DEFAULT_TIMEOUT,
                       redirect_uri: str = REDIRECT_URI_AUTH):

        self._client_id = client_id
        self.__client_secret = client_secret
        if not os.path.exists(ACCESS_TOKEN_FILE):
            access_token, refresh_token, expire_date = self.get_access_token(client_id=client_id,
                                                                             client_secret=client_secret,
                                                                             scope=scope,
                                                                             redirect_uri=redirect_uri,
                                                                             timeout=timeout)
            self.__credentials = {"access_token": access_token, "refresh_token": refresh_token,
                                  "expire_date": expire_date, "scope": sorted(scope)}
            with open(ACCESS_TOKEN_FILE, "w") as f:
                json.dump(self.__credentials, f)

            self.__headers = {
                "Authorization": f"Bearer {self.__credentials['access_token']}",
                "Client-Id": self._client_id,
                "Content-Type": "application/json"
            }
        else:
            with open(ACCESS_TOKEN_FILE, "r") as f:
                self.__credentials = json.load(f)

            if sorted(scope) != self.__credentials["scope"] or datetime.strptime(self.__credentials["expire_date"], '%d/%m/%Y') <= datetime.now():
                os.remove(ACCESS_TOKEN_FILE)
                self.authentication(client_id, client_secret, scope, timeout, redirect_uri)
                return

            self.__headers = {
                "Authorization": f"Bearer {self.__credentials['access_token']}",
                "Client-Id": self._client_id,
                "Content-Type": "application/json"
            }
