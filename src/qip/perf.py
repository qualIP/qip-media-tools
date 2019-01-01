__all__ = (
        'perfcontext',
        )

import time
from contextlib import contextmanager

from qip.app import app

@contextmanager
def perfcontext(name):
    t0 = time.perf_counter()
    try:
        yield
    finally:
        t1 = time.perf_counter()
        td = t1 - t0
        app.log.debug("PERF: %s: %.6fs", name, td)
