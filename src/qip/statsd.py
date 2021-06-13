#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

# https://statsd.readthedocs.io/en/latest/index.html

__all__ = [
]

import qip  # Executable support

import statsd

if __name__ == "__main__":
    import logging
    import random
    import re
    import sys
    import time
    from qip.app import app
    from qip.perf import perfcontext

    @app.main_wrapper
    def main():

        sys.argv[1:1] = [
            '--statsd',
            '--statsd-host', 'localhost',
        ]
        app.init(
            prog='qip-statsd-test',
            logging_level=logging.DEBUG,
            statsd_host='localhost',
        )
        app.parse_args()

        assert app.statsd, 'StatsD client not initialized'

        print(f'Run `nc -kulp {app.args.statsd_port}` on {app.args.statsd_host}')

        app.statsd.incr('foo')  # Increment the 'foo' counter.
        app.statsd.timing('stats.timed', 320)  # Record a 320ms 'stats.timed'.
        time.sleep(2)
        app.statsd.incr('bar')
        app.statsd.incr('baz')
        app.statsd.incr('asjdh')
        app.statsd.incr('asd')
        app.statsd.incr('jkl')

        from qip.perf import perfcontext
        for n in range(10):
            with perfcontext('test-timing', stat='timing1'):
                time.sleep(random.randrange(500) / 1000)

        with app.statsd.pipeline() as pipe:
            for n in range(10):
                pipe.set('test-set', str(random.randrange(3)))

    main()
