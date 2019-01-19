__all__ = (
        'ExcThread',
        )

import threading

class ExcThread(threading.Thread):

    def __init__(self, *, target=None, **kwargs):
        self._exc_target = target
        self._exc = None
        super().__init__(
                target=target and self._exc_target_wrapper,
                **kwargs)

    def _exc_target_wrapper(self, *args, **kwargs):
        try:
            self._exc_target(*args, **kwargs)
        except BaseException as e:
            self._exc = e

    def join(self, **kwargs):
        super().join(**kwargs)
        exc = self._exc
        if exc:
            raise exc
