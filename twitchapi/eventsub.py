import threading
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
import logging
import sqlite3

DEFAULT_ADDRESS = "0.0.0.0"
DEFAULT_PORT = 3000

MESSAGE_ENDPOINT = "/message"
REDIRECT_URI_MESSAGE = f"https://localhost:{DEFAULT_PORT}{MESSAGE_ENDPOINT}"

# message_db = sqlite3.connect('TwitchDatabase/message.db')
# follower_db = sqlite3.connect('TwitchDatabase/follower.db')

class WebRequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):

        logging.info(f'client:  {self.client_address}')
        logging.info(f'command: {self.command}')
        logging.info(f'path:    {self.path}')

        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)

        if url.path == MESSAGE_ENDPOINT:
            logging.info('Receive message!')
            logging.debug(query)

        self.send_response(HTTPStatus.OK)

    def do_POST(self):
        return self.do_GET()

class EventSub():
    def __init__(self,
                 address=DEFAULT_ADDRESS,
                 port=DEFAULT_PORT):

        self.address = address
        self.port = port
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