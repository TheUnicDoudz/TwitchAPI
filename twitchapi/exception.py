"""
Custom exceptions for Twitch API operations and bot functionality.

This module defines all custom exceptions used throughout the Twitch bot framework.
Each exception provides specific information about different types of failures
that can occur during API operations, authentication, or event processing.

Author: TheUnicDoudz
"""

from typing import Optional, Dict, Any


class TwitchBotException(Exception):
    """
    Base exception class for all Twitch bot related errors.

    This serves as the parent class for all custom exceptions in the framework,
    providing common functionality and allowing for broad exception handling.
    """

    def __init__(self, message: str, error_code: Optional[str] = None,
                 details: Optional[Dict[str, Any]] = None):
        """
        Initialize the base Twitch bot exception.

        Args:
            message: Human-readable error message
            error_code: Optional error code for programmatic handling
            details: Optional dictionary with additional error details
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}

    def __str__(self) -> str:
        """Return string representation of the exception."""
        if self.error_code:
            return f"[{self.error_code}] {self.message}"
        return self.message

    def __repr__(self) -> str:
        """Return detailed string representation for debugging."""
        return f"{self.__class__.__name__}(message='{self.message}', error_code='{self.error_code}', details={self.details})"


class TwitchAuthorizationFailed(TwitchBotException):
    """
    Exception raised when OAuth2 authorization process fails.

    This exception is raised during various stages of the OAuth2 flow:
    - Initial authorization request failures
    - Token exchange failures
    - Invalid client credentials
    - Insufficient permissions
    - Network errors during authentication

    Examples:
        - Invalid client ID or secret
        - User denied authorization
        - Redirect URI mismatch
        - Expired authorization codes
        - Network connectivity issues
    """

    def __init__(self, message: str, error_code: Optional[str] = None,
                 auth_url: Optional[str] = None, redirect_uri: Optional[str] = None):
        """
        Initialize authorization failure exception.

        Args:
            message: Human-readable error message
            error_code: Optional OAuth2 error code
            auth_url: URL that was being accessed when error occurred
            redirect_uri: Redirect URI that was configured
        """
        details = {}
        if auth_url:
            details['auth_url'] = auth_url
        if redirect_uri:
            details['redirect_uri'] = redirect_uri

        super().__init__(message, error_code, details)
        self.auth_url = auth_url
        self.redirect_uri = redirect_uri


class TwitchAuthentificationError(TwitchBotException):
    """
    Exception raised when authentication is invalid or has expired.

    This exception occurs when:
    - Access tokens have expired
    - Refresh tokens are invalid
    - API requests fail due to authentication issues
    - Insufficient permissions for requested operations
    - Token revocation by user

    This is different from TwitchAuthorizationFailed in that authorization
    was previously successful, but the current authentication state is invalid.
    """

    def __init__(self, message: str, error_code: Optional[str] = None,
                 token_expired: bool = False, refresh_attempted: bool = False):
        """
        Initialize authentication error exception.

        Args:
            message: Human-readable error message
            error_code: Optional API error code
            token_expired: Whether the error is due to token expiration
            refresh_attempted: Whether token refresh was attempted
        """
        details = {
            'token_expired': token_expired,
            'refresh_attempted': refresh_attempted
        }

        super().__init__(message, error_code, details)
        self.token_expired = token_expired
        self.refresh_attempted = refresh_attempted


class TwitchEndpointError(TwitchBotException):
    """
    Exception raised when Twitch API endpoint requests fail.

    This exception covers various API-related failures:
    - Invalid or malformed API requests
    - Rate limiting violations
    - Server-side errors (5xx responses)
    - Invalid endpoints or parameters
    - Network connectivity issues
    - Unexpected API responses
    """

    def __init__(self, message: str, error_code: Optional[str] = None,
                 endpoint: Optional[str] = None, status_code: Optional[int] = None,
                 response_data: Optional[Dict[str, Any]] = None):
        """
        Initialize API endpoint error exception.

        Args:
            message: Human-readable error message
            error_code: Optional API error code
            endpoint: API endpoint that failed
            status_code: HTTP status code returned
            response_data: Raw response data from API
        """
        details = {}
        if endpoint:
            details['endpoint'] = endpoint
        if status_code:
            details['status_code'] = status_code
        if response_data:
            details['response_data'] = response_data

        super().__init__(message, error_code, details)
        self.endpoint = endpoint
        self.status_code = status_code
        self.response_data = response_data

    def is_rate_limited(self) -> bool:
        """Check if the error is due to rate limiting."""
        return self.status_code == 429 or 'rate limit' in self.message.lower()

    def is_server_error(self) -> bool:
        """Check if the error is a server-side error (5xx)."""
        return self.status_code is not None and 500 <= self.status_code < 600

    def is_client_error(self) -> bool:
        """Check if the error is a client-side error (4xx)."""
        return self.status_code is not None and 400 <= self.status_code < 500


class TwitchMessageNotSentWarning(TwitchBotException):
    """
    Exception raised when a chat message cannot be sent.

    This exception is raised when message sending fails due to:
    - Chat restrictions (slow mode, subscriber only, etc.)
    - Message content violations
    - User banned or timed out
    - Rate limiting on messages
    - Invalid message format
    - Bot lacks necessary permissions

    This is typically a warning-level exception that doesn't indicate
    a critical system failure, but rather a temporary or policy-based
    restriction on message sending.
    """

    def __init__(self, message: str, error_code: Optional[str] = None,
                 drop_reason: Optional[str] = None, message_text: Optional[str] = None):
        """
        Initialize message sending warning exception.

        Args:
            message: Human-readable error message
            error_code: Twitch error code for message drop
            drop_reason: Specific reason why message was dropped
            message_text: The message text that failed to send
        """
        details = {}
        if drop_reason:
            details['drop_reason'] = drop_reason
        if message_text:
            details['message_text'] = message_text[:100]  # Truncate for privacy

        super().__init__(message, error_code, details)
        self.drop_reason = drop_reason
        self.message_text = message_text

    def is_rate_limited(self) -> bool:
        """Check if message was dropped due to rate limiting."""
        return (self.drop_reason and 'rate' in self.drop_reason.lower()) or \
            (self.error_code and self.error_code == 'msg_ratelimit')

    def is_banned(self) -> bool:
        """Check if message was dropped because user is banned."""
        return (self.drop_reason and 'ban' in self.drop_reason.lower()) or \
            (self.error_code and self.error_code == 'msg_banned')


class TwitchEventSubError(TwitchBotException):
    """
    Exception raised when EventSub WebSocket operations fail.

    This exception covers EventSub-specific failures:
    - WebSocket connection failures
    - Invalid subscription requests
    - EventSub service unavailability
    - Malformed event data
    - Session management errors
    - Subscription limit exceeded
    """

    def __init__(self, message: str, error_code: Optional[str] = None,
                 event_type: Optional[str] = None, session_id: Optional[str] = None,
                 websocket_error: Optional[Exception] = None):
        """
        Initialize EventSub error exception.

        Args:
            message: Human-readable error message
            error_code: EventSub specific error code
            event_type: Type of event that caused the error
            session_id: WebSocket session ID if available
            websocket_error: Underlying WebSocket exception if any
        """
        details = {}
        if event_type:
            details['event_type'] = event_type
        if session_id:
            details['session_id'] = session_id
        if websocket_error:
            details['websocket_error'] = str(websocket_error)

        super().__init__(message, error_code, details)
        self.event_type = event_type
        self.session_id = session_id
        self.websocket_error = websocket_error


class TwitchDatabaseError(TwitchBotException):
    """
    Exception raised when database operations fail.

    This exception covers database-related failures:
    - SQLite connection issues
    - Database corruption
    - Disk space issues
    - Lock timeout errors
    - Invalid SQL operations
    - Data integrity violations
    """

    def __init__(self, message: str, error_code: Optional[str] = None,
                 db_path: Optional[str] = None, sql_query: Optional[str] = None,
                 sqlite_error: Optional[Exception] = None):
        """
        Initialize database error exception.

        Args:
            message: Human-readable error message
            error_code: Database specific error code
            db_path: Path to database file
            sql_query: SQL query that caused the error (truncated for security)
            sqlite_error: Underlying SQLite exception
        """
        details = {}
        if db_path:
            details['db_path'] = db_path
        if sql_query:
            # Truncate query for security and readability
            details['sql_query'] = sql_query[:200] + ('...' if len(sql_query) > 200 else '')
        if sqlite_error:
            details['sqlite_error'] = str(sqlite_error)

        super().__init__(message, error_code, details)
        self.db_path = db_path
        self.sql_query = sql_query
        self.sqlite_error = sqlite_error


class TwitchConfigurationError(TwitchBotException):
    """
    Exception raised when bot configuration is invalid.

    This exception is raised for configuration-related issues:
    - Missing required configuration values
    - Invalid configuration formats
    - Conflicting configuration options
    - Unsupported feature combinations
    - Environment setup issues
    """

    def __init__(self, message: str, error_code: Optional[str] = None,
                 config_key: Optional[str] = None, config_value: Optional[str] = None):
        """
        Initialize configuration error exception.

        Args:
            message: Human-readable error message
            error_code: Configuration specific error code
            config_key: Configuration key that caused the error
            config_value: Invalid configuration value (truncated for security)
        """
        details = {}
        if config_key:
            details['config_key'] = config_key
        if config_value:
            # Truncate and mask sensitive values
            if any(sensitive in config_key.lower() for sensitive in ['secret', 'token', 'password']):
                details['config_value'] = '***MASKED***'
            else:
                details['config_value'] = str(config_value)[:100]

        super().__init__(message, error_code, details)
        self.config_key = config_key
        self.config_value = config_value


class KillThreadException(Exception):
    """
    Exception used to gracefully terminate threads.

    This exception is used internally to signal that a thread should
    terminate gracefully. It's raised using the ThreadWithExc class
    to interrupt long-running operations and allow for clean shutdown.

    This is not a subclass of TwitchBotException because it's used
    for internal thread management rather than error reporting.
    """

    def __init__(self, message: str = "Thread termination requested"):
        """
        Initialize thread termination exception.

        Args:
            message: Optional message explaining the termination reason
        """
        super().__init__(message)


# Utility functions for exception handling

def is_recoverable_error(exception: Exception) -> bool:
    """
    Determine if an exception represents a recoverable error.

    Recoverable errors are those that might succeed if retried,
    such as network timeouts or temporary service unavailability.

    Args:
        exception: Exception to analyze

    Returns:
        True if the error might be recoverable with retry, False otherwise
    """
    if isinstance(exception, TwitchEndpointError):
        # Server errors and some client errors are potentially recoverable
        return exception.is_server_error() or exception.is_rate_limited()

    if isinstance(exception, TwitchEventSubError):
        # WebSocket errors are often recoverable with reconnection
        return True

    if isinstance(exception, TwitchDatabaseError):
        # Some database errors like locks might be recoverable
        if exception.sqlite_error:
            error_msg = str(exception.sqlite_error).lower()
            return 'locked' in error_msg or 'busy' in error_msg

    # Authentication and configuration errors are generally not recoverable
    return False


def should_retry_operation(exception: Exception, attempt_count: int, max_attempts: int = 3) -> bool:
    """
    Determine if an operation should be retried based on the exception and attempt count.

    Args:
        exception: Exception that occurred
        attempt_count: Current attempt number (1-based)
        max_attempts: Maximum number of attempts allowed

    Returns:
        True if operation should be retried, False otherwise
    """
    if attempt_count >= max_attempts:
        return False

    return is_recoverable_error(exception)


def get_retry_delay(exception: Exception, attempt_count: int) -> float:
    """
    Calculate appropriate delay before retrying an operation.

    Uses exponential backoff with jitter for most errors,
    with special handling for rate limiting.

    Args:
        exception: Exception that occurred
        attempt_count: Current attempt number (1-based)

    Returns:
        Delay in seconds before next retry attempt
    """
    import random

    # Special handling for rate limiting
    if isinstance(exception, (TwitchEndpointError, TwitchMessageNotSentWarning)):
        if hasattr(exception, 'is_rate_limited') and exception.is_rate_limited():
            # Longer delay for rate limiting
            base_delay = 60  # 1 minute base delay
            return base_delay * (2 ** (attempt_count - 1)) + random.uniform(0, 10)

    # Exponential backoff with jitter for other errors
    base_delay = 1  # 1 second base delay
    max_delay = 300  # 5 minutes maximum delay

    delay = min(base_delay * (2 ** (attempt_count - 1)), max_delay)
    jitter = random.uniform(0, delay * 0.1)  # 10% jitter

    return delay + jitter


def format_exception_for_logging(exception: Exception) -> str:
    """
    Format an exception for structured logging.

    Args:
        exception: Exception to format

    Returns:
        Formatted string suitable for logging
    """
    if isinstance(exception, TwitchBotException):
        parts = [f"{exception.__class__.__name__}: {exception.message}"]

        if exception.error_code:
            parts.append(f"Code: {exception.error_code}")

        if exception.details:
            detail_strs = []
            for key, value in exception.details.items():
                detail_strs.append(f"{key}={value}")
            if detail_strs:
                parts.append(f"Details: {', '.join(detail_strs)}")

        return " | ".join(parts)
    else:
        return f"{exception.__class__.__name__}: {str(exception)}"