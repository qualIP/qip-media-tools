# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = (
        'perfcontext',
        'perfcontext_wrapper',
        )

import functools
import time
from contextlib import contextmanager

from .app import app
from .utils import Timestamp

class PerfTimer(object):

    t0 = None
    t1 = None

    @property
    def td(self):
        try:
            return self.t1 - self.t0
        except TypeError:
            return None

    @property
    def ms(self):
        try:
            return self.td * 1000
        except TypeError:
            return None

    def start(self):
        self.t0 = time.perf_counter();

    def stop(self):
        self.t1 = time.perf_counter();

    def __enter__(self):
        self.start()

    def __exit__(self, exc_type, exc_value, exc_traceback):
        self.stop()

    def __float__(self):
        return float(self.td)


@contextmanager
def perfcontext(name,
                log=False,
                stat=None, statsd=None, statsd_rate=1,
                ):
    if log:
        app.log.info('%s...', name)
    t = PerfTimer()
    stat_ret = f'unknown'
    try:
        try:
            with t:
                yield
        except BaseException as e:
            stat_ret = f'raise.{e.__class__.__name__}'
            raise
        else:
            stat_ret = f'success'
    finally:
        if stat:
            statsd = statsd or app.statsd
            if statsd:
                statsd.timing(stat=f'{stat}.{stat_ret}', delta=t.ms, rate=statsd_rate)
        app.log.debug("PERF: %s: %s", name, Timestamp(t.td))


def perfcontext_wrapper(name,
                        log=False,
                        stat=None, statsd=None, statsd_rate=1,
                        ):

    def outer(func):

        @functools.wraps(func)
        def inner(*args, **kwargs):
            with perfcontext(name, log=log, stat=stat, statsd=statsd, statsd_rate=statsd_rate):
                return func(*args, **kwargs)

        return inner

    return outer
