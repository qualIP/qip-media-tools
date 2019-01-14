__all__ = (
        'perfcontext',
        )

import time
from contextlib import contextmanager

from .app import app
from .utils import Timestamp

@contextmanager
def perfcontext(name):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        t1 = time.perf_counter()
        td = t1 - t0
        app.log.debug("PERF: %s: %s", name, Timestamp(td))
