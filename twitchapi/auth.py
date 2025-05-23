"""
Authentication module for Twitch API using OAuth2.

This module provides an AuthServer class to handle OAuth2 authentication
with the Twitch API, including access token management and renewal.

Author: TheUnicDoudz
Thanks: Quadricopter (https://github.com/Quadricopter) for OAuth2 help
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import webbrowser
import requests
import secrets
import urllib.parse
import threading
import logging
import time
import json
import os
from datetime import datetime, timedelta
from collections.abc import Callable
from random import randint
from typing import Optional, Dict, List, Any

from requests import Response
from http import HTTPStatus

from twitchapi.exception import (
    TwitchAuthorizationFailed,
    TwitchAuthentificationError,
    TwitchEndpointError
)
from twitchapi.twitchcom import TwitchEndpoint

# Default configuration
DEFAULT_ADDRESS = "0.0.0.0"
DEFAULT_PORT = 8000
REDIRECT_URI_AUTH = f"http://localhost:{DEFAULT_PORT}/oauth2callback"
DEFAULT_TIMEOUT = 600
ACCESS_TOKEN_FILE = ".access_token"

# Global dictionary to store temporary authorization codes
code_dict: Dict[str, str] = {}


class WebRequestHandler(BaseHTTPRequestHandler):
    """
    HTTP request handler for OAuth2 callback server.

    This server captures authorization codes returned by Twitch
    after user authentication.
    """

    def do_GET(self) -> None:
        """
        Handles GET requests sent to the callback server.

        Extracts the authorization code from the callback URL and stores it
        in the global dictionary for later retrieval.
        """
        try:
            logging.info(f'Client connection: {self.client_address}')
            logging.info(f'Command: {self.command}')
            logging.info(f'Path: {self.path}')

            # Parse URL to extract parameters
            url = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(url.query)

            if url.path == "/oauth2callback":
                logging.info('OAuth2 callback received!')
                logging.debug(f'Query parameters: {query}')

                # Check for required parameters
                if 'state' in query and 'code' in query:
                    logging.info("Authorization code provided!")
                    state = query['state'][0]
                    code_dict[state] = query['code'][0]
                else:
                    logging.error("Missing parameters in callback request")
                    if 'error' in query:
                        logging.error(f"OAuth2 error: {query['error'][0]}")

            # Send HTTP response
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-type', 'text/html')
            self.end_headers()

            # Confirmation message for user
            response_html = """
            <html>
                <body>
                    <h2>Authentication successful!</h2>
                    <p>You can close this window.</p>
                </body>
            </html>
            """
            self.wfile.write(response_html.encode())

        except Exception as e:
            logging.error(f"Error in callback handler: {e}")
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR)

    def log_message(self, format: str, *args) -> None:
        """Suppress default HTTP server logs to avoid spam."""
        pass


class AuthServer:
    """
    Authentication server for Twitch API.

    This class handles the entire OAuth2 authentication process,
    including starting a local callback server, obtaining access tokens,
    renewing them, and managing requests to the Twitch API.
    """

    def __init__(self,
                 address: str = DEFAULT_ADDRESS,
                 port: int = DEFAULT_PORT,
                 start: bool = False) -> None:
        """
        Initialize the authentication server.

        Args:
            address: IP address of the callback server
            port: Port of the callback server
            start: If True, automatically start the server
        """
        self.address = address
        self.port = port
        self._client_id: Optional[str] = None
        self.__client_secret: Optional[str] = None
        self.__credentials: Optional[Dict[str, Any]] = None
        self.__headers: Optional[Dict[str, str]] = None
        self.__token_file_path: Optional[str] = None
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[threading.Thread] = None

        if start:
            self.start()

    def __http_thread(self) -> None:
        """
        Start HTTP server in a separate thread.

        This server listens on the configured port to receive OAuth2
        callbacks from Twitch.
        """
        try:
            self.server = HTTPServer(('', self.port), WebRequestHandler)
            logging.info(f'Callback server started on {self.server.server_address}')

            self.server.serve_forever()
        except KeyboardInterrupt:
            logging.info("Server shutdown requested by user")
        except Exception as e:
            logging.error(f"Error in HTTP thread: {e}")
        finally:
            logging.info('HTTP thread shutting down')

    def start(self) -> None:
        """Start the callback server in a separate thread."""
        if self.thread and self.thread.is_alive():
            logging.warning("Server is already running")
            return

        self.thread = threading.Thread(target=self.__http_thread, daemon=True)
        self.thread.start()

        # Wait for server to be ready
        time.sleep(0.5)

    def stop(self) -> None:
        """
        Stop the callback server and clean up resources.
        """
        if not self.server:
            logging.warning("No server to stop")
            return

        try:
            logging.info('Stopping server...')
            self.server.shutdown()

            if self.thread and self.thread.is_alive():
                logging.info('Waiting for thread to finish...')
                self.thread.join(timeout=5.0)

            if self.server:
                self.server.server_close()

            logging.info('Server stopped successfully!')

        except Exception as e:
            logging.error(f"Error stopping server: {e}")

    def get_access_token(self,
                         client_id: str,
                         client_secret: str,
                         scope: List[str],
                         redirect_uri: str = REDIRECT_URI_AUTH,
                         timeout: int = DEFAULT_TIMEOUT) -> None:
        """
        Obtain an access token via Twitch's OAuth2 protocol.

        Args:
            client_id: Twitch application ID
            client_secret: Twitch application secret
            scope: List of requested permissions
            redirect_uri: Redirect URI for callback
            timeout: Timeout in seconds

        Raises:
            TwitchAuthorizationFailed: On authorization failure
        """
        if not client_id or not client_secret:
            raise ValueError("client_id and client_secret are required")

        if not scope:
            raise ValueError("At least one scope is required")

        code = None
        twitch_code_url = TwitchEndpoint.TWITCH_AUTH_URL + TwitchEndpoint.CODE
        twitch_token_url = TwitchEndpoint.TWITCH_AUTH_URL + TwitchEndpoint.TOKEN

        try:
            # Generate secure state to prevent CSRF attacks
            state_length = randint(16, 32)
            state = secrets.token_urlsafe(state_length)

            # Build authorization parameters
            code_auth_params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(scope),
                "state": state
            }

            code_auth_params_str = urllib.parse.urlencode(code_auth_params)
            logging.debug(f"Authorization parameters: {code_auth_params_str}")

            # Request authorization code
            auth_url = f"{twitch_code_url}?{code_auth_params_str}"
            logging.info("Opening Twitch authentication page...")
            logging.debug(f"Authentication URL: {auth_url}")

            # Check that URL is accessible
            response = requests.head(twitch_code_url, timeout=10)
            if response.status_code != 200:
                raise TwitchAuthorizationFailed(
                    "Unable to access Twitch authentication service"
                )

            # Open browser
            if not webbrowser.open_new(auth_url):
                logging.warning("Unable to open browser automatically")
                print(f"Please manually open this URL: {auth_url}")

            logging.info("Waiting for authorization code...")

            # Start callback server
            self.start()

            # Wait for authorization code with timeout
            start_time = time.time()
            while time.time() - start_time < timeout:
                if state in code_dict:
                    code = code_dict.pop(state)
                    logging.info("Authorization code received!")
                    break
                time.sleep(1)

            if code is None:
                raise TwitchAuthorizationFailed(
                    f"Timeout exceeded ({timeout}s). "
                    "Check redirect URI and try again."
                )

        except KeyboardInterrupt:
            raise TwitchAuthorizationFailed("Authentication cancelled by user")
        finally:
            self.stop()

        # Exchange code for access token
        try:
            token_auth_params = {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri
            }

            logging.info("Exchanging code for access token...")
            response = requests.post(
                twitch_token_url,
                data=token_auth_params,
                timeout=30
            )

            if response.status_code != 200:
                logging.error(f"Token exchange error: {response.text}")
                raise TwitchAuthorizationFailed(
                    "Failed to obtain access token. "
                    "Check your application's client_secret."
                )

            token_data = response.json()

            # Validate response
            required_fields = ["access_token", "refresh_token"]
            for field in required_fields:
                if field not in token_data:
                    raise TwitchAuthorizationFailed(f"Missing field in response: {field}")

            access_token = token_data["access_token"]
            refresh_token = token_data["refresh_token"]

            # Calculate expiry date (25 days to be safe)
            expire_date = (datetime.now() + timedelta(days=25)).strftime('%d/%m/%Y')

            logging.info('Access token obtained successfully!')
            logging.debug(f"Token: {access_token[:10]}...")

            # Save credentials
            self.__credentials = {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expire_date": expire_date,
                "scope": scope
            }

            self._save_credentials()
            self._update_headers()

        except requests.RequestException as e:
            logging.error(f"Network error during token exchange: {e}")
            raise TwitchAuthorizationFailed("Network error during authentication")
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON response: {e}")
            raise TwitchAuthorizationFailed("Invalid response from Twitch server")

    def refresh_token(self) -> None:
        """
        Refresh the access token using the refresh token.

        Raises:
            TwitchAuthorizationFailed: On refresh failure
        """
        if not self.__credentials or not self.__credentials.get("refresh_token"):
            raise TwitchAuthorizationFailed("No refresh token available")

        twitch_token_url = TwitchEndpoint.TWITCH_AUTH_URL + TwitchEndpoint.TOKEN

        token_auth_params = {
            "client_id": self._client_id,
            "client_secret": self.__client_secret,
            "grant_type": "refresh_token",
            "refresh_token": self.__credentials["refresh_token"]
        }

        try:
            logging.info("Refreshing access token...")
            response = requests.post(
                twitch_token_url,
                data=token_auth_params,
                timeout=30
            )

            if response.status_code != 200:
                logging.error(f"Token refresh error: {response.text}")
                raise TwitchAuthorizationFailed(
                    "Failed to refresh token. "
                    "New authentication may be required."
                )

            token_data = response.json()

            # Validate response
            if "access_token" not in token_data:
                raise TwitchAuthorizationFailed("Access token missing in response")

            access_token = token_data["access_token"]
            refresh_token = token_data.get("refresh_token", self.__credentials["refresh_token"])
            expire_date = (datetime.now() + timedelta(days=25)).strftime('%d/%m/%Y')

            # Update credentials
            self.__credentials.update({
                "access_token": access_token,
                "refresh_token": refresh_token,
                "expire_date": expire_date
            })

            self._save_credentials()
            self._update_headers()

            logging.info("Token refreshed successfully!")

        except requests.RequestException as e:
            logging.error(f"Network error during token refresh: {e}")
            raise TwitchAuthorizationFailed("Network error during token refresh")
        except json.JSONDecodeError as e:
            logging.error(f"Invalid JSON response during refresh: {e}")
            raise TwitchAuthorizationFailed("Invalid response from Twitch server")

    def _save_credentials(self) -> None:
        """Save credentials to specified file."""
        if not self.__token_file_path or not self.__credentials:
            return

        try:
            # Create directory if necessary
            os.makedirs(os.path.dirname(self.__token_file_path), exist_ok=True)

            with open(self.__token_file_path, "w", encoding='utf-8') as f:
                json.dump(self.__credentials, f, indent=2)

        except IOError as e:
            logging.error(f"Error saving credentials: {e}")

    def _update_headers(self) -> None:
        """Update HTTP headers for API requests."""
        if not self.__credentials or not self._client_id:
            return

        self.__headers = {
            "Authorization": f"Bearer {self.__credentials['access_token']}",
            "Client-Id": self._client_id,
            "Content-Type": "application/json"
        }

    @staticmethod
    def __check_request(request_function: Callable) -> Callable:
        """
        Decorator that checks token validity and refreshes if necessary.

        Args:
            request_function: Request function to decorate

        Returns:
            Decorated function with automatic token management
        """

        def wrapper(self, endpoint: str, data: Optional[Dict] = None) -> Dict[str, Any]:
            if not self.__headers:
                raise TwitchAuthentificationError("No authentication configured")

            full_endpoint = TwitchEndpoint.TWITCH_ENDPOINT + endpoint
            params = {"self": self, "endpoint": full_endpoint}

            if data:
                params["data"] = data

            try:
                # First attempt
                response = request_function(**params)

                if 200 <= response.status_code < 300:
                    return response.json()

                # Handle authentication errors
                if response.status_code == 401:
                    logging.warning("Token expired, attempting refresh...")
                    self.refresh_token()

                    # Second attempt after refresh
                    response = request_function(**params)

                    if 200 <= response.status_code < 300:
                        return response.json()
                    else:
                        logging.error(f"Failed after refresh: {response.text}")
                        raise TwitchAuthentificationError(
                            "Authentication failed even after token refresh"
                        )
                else:
                    logging.error(f"API error: {response.status_code} - {response.text}")
                    raise TwitchEndpointError(
                        f"Error {response.status_code}: {endpoint} - "
                        "Check URL and permissions"
                    )

            except requests.RequestException as e:
                logging.error(f"Network error during request: {e}")
                raise TwitchEndpointError(f"Network error: {e}")

        return wrapper

    @__check_request
    def get_request(self, endpoint: str) -> Response:
        """
        Make a GET request to Twitch API.

        Args:
            endpoint: Twitch API endpoint

        Returns:
            API response
        """
        return requests.get(url=endpoint, headers=self.__headers, timeout=30)

    @__check_request
    def post_request(self, endpoint: str, data: Dict[str, Any]) -> Response:
        """
        Make a POST request to Twitch API.

        Args:
            endpoint: Twitch API endpoint
            data: Data to send

        Returns:
            API response
        """
        return requests.post(url=endpoint, json=data, headers=self.__headers, timeout=30)

    def authentication(self,
                       client_id: str,
                       client_secret: str,
                       scope: List[str],
                       token_file_path: str = ACCESS_TOKEN_FILE,
                       timeout: int = DEFAULT_TIMEOUT,
                       redirect_uri: str = REDIRECT_URI_AUTH) -> None:
        """
        Configure authentication and obtain access token if necessary.

        Args:
            client_id: Twitch application ID
            client_secret: Twitch application secret
            scope: List of requested permissions
            token_file_path: Path to token save file
            timeout: Authentication timeout
            redirect_uri: Redirect URI for callback
        """
        # Parameter validation
        if not client_id or not client_secret:
            raise ValueError("client_id and client_secret are required")

        if not scope:
            raise ValueError("At least one scope is required")

        self._client_id = client_id
        self.__client_secret = client_secret
        self.__token_file_path = token_file_path

        # Check for saved token
        if os.path.exists(self.__token_file_path):
            try:
                with open(self.__token_file_path, "r", encoding='utf-8') as f:
                    self.__credentials = json.load(f)

                # Validate saved token
                if self._is_token_valid(scope):
                    logging.info("Valid token found, using existing token")
                    self._update_headers()
                    return
                else:
                    logging.info("Invalid or expired token, new authentication required")
                    self._remove_invalid_token()

            except (json.JSONDecodeError, IOError) as e:
                logging.warning(f"Error reading token: {e}")
                self._remove_invalid_token()

        # Get new token
        self.get_access_token(
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
            redirect_uri=redirect_uri,
            timeout=timeout
        )

    def _is_token_valid(self, required_scope: List[str]) -> bool:
        """
        Check if saved token is valid.

        Args:
            required_scope: Required permissions

        Returns:
            True if token is valid, False otherwise
        """
        if not self.__credentials:
            return False

        try:
            # Check required fields
            required_fields = ["access_token", "refresh_token", "expire_date", "scope"]
            for field in required_fields:
                if field not in self.__credentials:
                    logging.warning(f"Missing field in token: {field}")
                    return False

            # Check expiry date
            expire_date = datetime.strptime(self.__credentials["expire_date"], '%d/%m/%Y')
            if expire_date <= datetime.now():
                logging.info("Token expired")
                return False

            # Check permissions
            saved_scope = set(self.__credentials["scope"])
            required_scope_set = set(required_scope)

            if not required_scope_set.issubset(saved_scope):
                logging.info("Insufficient permissions in saved token")
                return False

            return True

        except (ValueError, TypeError) as e:
            logging.warning(f"Error validating token: {e}")
            return False

    def _remove_invalid_token(self) -> None:
        """Remove invalid token file."""
        if self.__token_file_path and os.path.exists(self.__token_file_path):
            try:
                os.remove(self.__token_file_path)
                logging.info("Invalid token removed")
            except OSError as e:
                logging.warning(f"Unable to remove invalid token: {e}")

    def is_authenticated(self) -> bool:
        """
        Check if authentication is active.

        Returns:
            True if authenticated, False otherwise
        """
        return bool(self.__headers and self.__credentials)

    def get_current_scopes(self) -> List[str]:
        """
        Return current token permissions.

        Returns:
            List of permissions
        """
        if self.__credentials and "scope" in self.__credentials:
            return self.__credentials["scope"]
        return []

    def __del__(self) -> None:
        """Automatic cleanup when object is destroyed."""
        try:
            self.stop()
        except:
            pass  # Ignore errors during cleanup