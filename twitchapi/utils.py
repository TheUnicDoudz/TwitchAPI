"""
Utility classes and functions for thread management and callback handling.

This module provides enhanced thread management with exception raising capabilities
and a trigger mapping system for event callbacks.

Author: TheUnicDoudz
"""

import threading
import inspect
import ctypes
import logging
from collections.abc import Callable
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def _async_raise(tid: int, exctype: type) -> None:
    """
    Raise an exception in a thread with the given thread ID.

    This function uses the Python C API to asynchronously raise an exception
    in another thread. This is used for graceful thread termination.

    Args:
        tid: Thread ID where the exception should be raised
        exctype: Exception class to raise

    Raises:
        TypeError: If exctype is not a class
        ValueError: If thread ID is invalid
        SystemError: If the operation fails

    Warning:
        This function uses low-level Python C API and should be used carefully.
        It may not work in all Python implementations or versions.
    """
    if not inspect.isclass(exctype):
        raise TypeError("Only exception classes can be raised (not instances)")

    try:
        # Use Python's C API to raise exception in target thread
        res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_long(tid),
            ctypes.py_object(exctype)
        )

        if res == 0:
            raise ValueError("Invalid thread ID - thread not found")
        elif res != 1:
            # If it returns a number greater than one, we're in trouble
            # Call it again with exc=NULL to revert the effect
            ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), None)
            raise SystemError("PyThreadState_SetAsyncExc failed - multiple threads affected")

        logger.debug(f"Successfully raised {exctype.__name__} in thread {tid}")

    except Exception as e:
        logger.error(f"Failed to raise exception in thread {tid}: {e}")
        raise


class ThreadWithExc(threading.Thread):
    """
    Enhanced Thread class that supports raising exceptions from another thread.

    This class extends the standard threading.Thread to provide a mechanism
    for one thread to raise an exception in another thread's context.
    This is particularly useful for graceful thread termination.

    Example:
        def worker_function():
            try:
                while True:
                    # Do work
                    time.sleep(1)
            except CustomException:
                print("Thread terminated gracefully")

        thread = ThreadWithExc(target=worker_function)
        thread.start()

        # Later, to stop the thread:
        thread.raise_exc(CustomException)
        thread.join()
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize the enhanced thread.

        Args:
            *args: Arguments passed to threading.Thread
            **kwargs: Keyword arguments passed to threading.Thread
        """
        super().__init__(*args, **kwargs)
        self._thread_id = None
        self._exception_raised = False
        self._lock = threading.Lock()

    def _get_my_tid(self) -> int:
        """
        Determine this thread's ID.

        This method finds the thread ID for the current ThreadWithExc instance.
        It's executed in the context of the caller thread to get the identity
        of the thread represented by this instance.

        Returns:
            Thread ID as an integer

        Raises:
            threading.ThreadError: If thread is not active
            AssertionError: If thread ID cannot be determined
        """
        with self._lock:
            if not self.is_alive():
                raise threading.ThreadError("Thread is not active")

            # Return cached thread ID if available
            if self._thread_id is not None:
                return self._thread_id

            # Search for thread ID in active threads
            for tid, tobj in threading._active.items():
                if tobj is self:
                    self._thread_id = tid
                    logger.debug(f"Found thread ID: {tid}")
                    return tid

            # Fallback: try using ident attribute (Python 2.6+)
            if hasattr(self, 'ident') and self.ident is not None:
                self._thread_id = self.ident
                return self.ident

            raise AssertionError("Could not determine thread ID")

    def raise_exc(self, exctype: type) -> bool:
        """
        Raise an exception in this thread's context.

        This method raises the specified exception type in the context of
        this thread. If the thread is busy in a system call (time.sleep(),
        socket.accept(), etc.), the exception may be ignored until the
        system call completes.

        Args:
            exctype: Exception class to raise in the thread

        Returns:
            True if exception was successfully raised, False otherwise

        Raises:
            TypeError: If exctype is not an exception class
            ValueError: If thread is not active

        Example:
            class StopThread(Exception):
                pass

            # To ensure the thread stops:
            thread.raise_exc(StopThread)
            while thread.is_alive():
                time.sleep(0.1)
                thread.raise_exc(StopThread)
        """
        if not inspect.isclass(exctype) or not issubclass(exctype, BaseException):
            raise TypeError("exctype must be an exception class")

        with self._lock:
            if self._exception_raised:
                logger.warning("Exception already raised in this thread")
                return False

            try:
                tid = self._get_my_tid()
                _async_raise(tid, exctype)
                self._exception_raised = True
                logger.info(f"Raised {exctype.__name__} in thread {self.name or tid}")
                return True

            except Exception as e:
                logger.error(f"Failed to raise exception in thread: {e}")
                return False

    def is_exception_raised(self) -> bool:
        """
        Check if an exception has been raised in this thread.

        Returns:
            True if an exception has been raised, False otherwise
        """
        with self._lock:
            return self._exception_raised

    def join(self, timeout: Optional[float] = None) -> None:
        """
        Wait for the thread to terminate.

        This method extends the standard join() to provide better logging
        and timeout handling.

        Args:
            timeout: Maximum time to wait in seconds (None = wait forever)
        """
        try:
            super().join(timeout)

            if self.is_alive():
                logger.warning(f"Thread {self.name or self.ident} did not terminate within timeout")
            else:
                logger.debug(f"Thread {self.name or self.ident} terminated successfully")

        except Exception as e:
            logger.error(f"Error joining thread: {e}")

    def run(self) -> None:
        """
        Thread execution method with enhanced error handling.

        This method wraps the standard run() method to provide better
        error logging and cleanup.
        """
        try:
            logger.debug(f"Starting thread: {self.name or self.ident}")
            super().run()
            logger.debug(f"Thread completed: {self.name or self.ident}")

        except Exception as e:
            logger.error(f"Thread {self.name or self.ident} crashed: {e}")
            raise
        finally:
            # Reset exception flag when thread ends
            with self._lock:
                self._exception_raised = False


class TriggerMap:
    """
    Map event triggers to callback functions.

    This class provides a registry for mapping string-based trigger signals
    to callback functions. It's used for event-driven programming where
    different events need to trigger different callback functions.

    Example:
        def on_message(user, text):
            print(f"{user}: {text}")

        def on_follow(user):
            print(f"New follower: {user}")

        trigger_map = TriggerMap()
        trigger_map.add_trigger(on_message, "message")
        trigger_map.add_trigger(on_follow, "follow")

        # Later, trigger callbacks:
        trigger_map.trigger("message", {"user": "Alice", "text": "Hello!"})
        trigger_map.trigger("follow", {"user": "Bob"})
    """

    def __init__(self):
        """Initialize the trigger map with an empty callback registry."""
        self.__callbacks: Dict[str, Callable] = {}
        self.__lock = threading.RLock()  # Allow recursive locking

        logger.debug("TriggerMap initialized")

    def add_trigger(self, callback: Callable, trigger_value: str) -> None:
        """
        Register a callback function for a specific trigger signal.

        Args:
            callback: Function to call when trigger is activated
            trigger_value: String identifier for the trigger

        Raises:
            ValueError: If parameters are invalid
            KeyError: If trigger_value is already registered

        Example:
            def my_callback(param1, param2):
                print(f"Called with {param1}, {param2}")

            trigger_map.add_trigger(my_callback, "my_event")
        """
        if not callable(callback):
            raise ValueError("callback must be a callable function")

        if not isinstance(trigger_value, str) or not trigger_value.strip():
            raise ValueError("trigger_value must be a non-empty string")

        trigger_value = trigger_value.strip()

        with self.__lock:
            if trigger_value in self.__callbacks:
                existing_callback = self.__callbacks[trigger_value]
                raise KeyError(
                    f"Trigger '{trigger_value}' is already registered "
                    f"to callback '{existing_callback.__name__}'"
                )

            self.__callbacks[trigger_value] = callback
            logger.debug(f"Registered callback '{callback.__name__}' for trigger '{trigger_value}'")

    def remove_trigger(self, trigger_value: str) -> bool:
        """
        Remove a trigger and its associated callback.

        Args:
            trigger_value: String identifier for the trigger to remove

        Returns:
            True if trigger was removed, False if it didn't exist
        """
        if not isinstance(trigger_value, str):
            return False

        trigger_value = trigger_value.strip()

        with self.__lock:
            if trigger_value in self.__callbacks:
                callback = self.__callbacks.pop(trigger_value)
                logger.debug(f"Removed trigger '{trigger_value}' (callback: {callback.__name__})")
                return True
            return False

    def trigger(self, trigger_value: str, param: Optional[Dict[str, Any]] = None) -> bool:
        """
        Activate a trigger and call its associated callback.

        Args:
            trigger_value: String identifier for the trigger to activate
            param: Dictionary of parameters to pass to the callback

        Returns:
            True if callback was executed successfully, False otherwise

        Raises:
            KeyError: If trigger_value is not registered

        Example:
            # Callback with parameters
            trigger_map.trigger("my_event", {"param1": "value1", "param2": "value2"})

            # Callback without parameters
            trigger_map.trigger("simple_event")
        """
        if not isinstance(trigger_value, str) or not trigger_value.strip():
            raise ValueError("trigger_value must be a non-empty string")

        trigger_value = trigger_value.strip()

        with self.__lock:
            if trigger_value not in self.__callbacks:
                raise KeyError(f"No callback registered for trigger '{trigger_value}'")

            callback = self.__callbacks[trigger_value]

            try:
                if param and isinstance(param, dict):
                    # Call with parameters as keyword arguments
                    callback(**param)
                else:
                    # Call without parameters
                    callback()

                logger.debug(f"Successfully triggered '{trigger_value}'")
                return True

            except Exception as e:
                logger.error(f"Error executing callback for trigger '{trigger_value}': {e}")
                # Log the full traceback for debugging
                import traceback
                logger.debug(f"Callback error traceback:\n{traceback.format_exc()}")
                return False

    def has_trigger(self, trigger_value: str) -> bool:
        """
        Check if a trigger is registered.

        Args:
            trigger_value: String identifier for the trigger

        Returns:
            True if trigger is registered, False otherwise
        """
        if not isinstance(trigger_value, str):
            return False

        with self.__lock:
            return trigger_value.strip() in self.__callbacks

    def get_triggers(self) -> list[str]:
        """
        Get a list of all registered trigger values.

        Returns:
            List of trigger string identifiers
        """
        with self.__lock:
            return list(self.__callbacks.keys())

    def get_callback(self, trigger_value: str) -> Optional[Callable]:
        """
        Get the callback function for a specific trigger.

        Args:
            trigger_value: String identifier for the trigger

        Returns:
            Callback function if trigger exists, None otherwise
        """
        if not isinstance(trigger_value, str):
            return None

        with self.__lock:
            return self.__callbacks.get(trigger_value.strip())

    def clear(self) -> None:
        """Remove all registered triggers and callbacks."""
        with self.__lock:
            count = len(self.__callbacks)
            self.__callbacks.clear()
            logger.debug(f"Cleared {count} triggers from TriggerMap")

    def __len__(self) -> int:
        """Return the number of registered triggers."""
        with self.__lock:
            return len(self.__callbacks)

    def __contains__(self, trigger_value: str) -> bool:
        """Check if a trigger exists using 'in' operator."""
        return self.has_trigger(trigger_value)

    def __str__(self) -> str:
        """String representation showing registered triggers."""
        with self.__lock:
            triggers = list(self.__callbacks.keys())
            return f"TriggerMap({len(triggers)} triggers: {triggers})"

    def __repr__(self) -> str:
        """Detailed string representation for debugging."""
        with self.__lock:
            callbacks_info = []
            for trigger, callback in self.__callbacks.items():
                callbacks_info.append(f"'{trigger}': {callback.__name__}")
            return f"TriggerMap({{{', '.join(callbacks_info)}}})"