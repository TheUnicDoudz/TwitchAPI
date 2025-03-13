import threading
import inspect
import ctypes
from collections.abc import Callable

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
    Link callback to signal define by a specific string
    """
    def __init__(self):
        self.__callbacks = {}

    def add_trigger(self, callback: Callable, trigger_value: str):
        """
        Connect a callback to a trigger signal
        :param callback: function to call
        :param trigger_value: trigger signal value
        """
        if trigger_value in self.__callbacks:
            raise KeyError(f"There's already a callback react to {trigger_value}!!")
        self.__callbacks[trigger_value] = callback

    def trigger(self, trigger_value: str, param: dict=None):
        """
        Trigger a callback linked to a signal
        :param trigger_value: signal to trigger a callback
        :param param: parameter of the callback (optional)
        """
        if trigger_value not in self.__callbacks:
            raise KeyError(f"There's no callback react to {trigger_value}!!")
        if param:
            self.__callbacks[trigger_value](**param)
        else:
            self.__callbacks[trigger_value]()
