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


def _async_raise(tid, exctype):
    '''Raises an exception in the threads with id tid'''
    if not inspect.isclass(exctype):
        raise TypeError("Only types can be raised (not instances)")
    res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid),
                                                     ctypes.py_object(exctype))
    if res == 0:
        raise ValueError("invalid thread id")
    elif res != 1:
        # "if it returns a number greater than one, you're in trouble,
        # and you should call it again with exc=NULL to revert the effect"
        ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), None)
        raise SystemError("PyThreadState_SetAsyncExc failed")


class ThreadWithExc(threading.Thread):
    '''A thread class that supports raising an exception in the thread from
       another thread.
    '''

    def _get_my_tid(self):
        """determines this (self's) thread id

        CAREFUL: this function is executed in the context of the caller
        thread, to get the identity of the thread represented by this
        instance.
        """
        if not self.is_alive():  # Note: self.isAlive() on older version of Python
            raise threading.ThreadError("the thread is not active")

        # do we have it cached?
        if hasattr(self, "_thread_id"):
            return self._thread_id

        # no, look for it in the _active dict
        for tid, tobj in threading._active.items():
            if tobj is self:
                self._thread_id = tid
                return tid

        # TODO: in python 2.6, there's a simpler way to do: self.ident

        raise AssertionError("could not determine the thread's id")

    def raise_exc(self, exctype):
        """Raises the given exception type in the context of this thread.

        If the thread is busy in a system call (time.sleep(),
        socket.accept(), ...), the exception is simply ignored.

        If you are sure that your exception should terminate the thread,
        one way to ensure that it works is:

            t = ThreadWithExc( ... )
            ...
            t.raise_exc( SomeException )
            while t.isAlive():
                time.sleep( 0.1 )
                t.raise_exc( SomeException )

        If the exception is to be caught by the thread, you need a way to
        check that your thread has caught it.

        CAREFUL: this function is executed in the context of the
        caller thread, to raise an exception in the context of the
        thread represented by this instance.
        """
        _async_raise(self._get_my_tid(), exctype)

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