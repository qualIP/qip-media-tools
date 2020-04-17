#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK

from pathlib import Path
import logging
import os

from qip.cdrom import cdrom_ready
from qip import argparse
from qip.app import app

def _resolved_Path(path):
    return Path(path).resolve()

@app.main_wrapper
def main():

    app.init(
            version='1.0',
            description='CDROM ready checker',
            contact='jst@qualipsoft.com',
            )

    # TODO app.parser.add_argument('--help', '-h', action='help')
    app.parser.add_argument('--version', '-V', action='version')

    pgroup = app.parser.add_argument_group('Program Control')
    xgroup = pgroup.add_mutually_exclusive_group()
    xgroup.add_argument('--logging_level', default=argparse.SUPPRESS, help='set logging level')
    xgroup.add_argument('--quiet', '-q', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.WARNING, help='quiet mode')
    xgroup.add_argument('--verbose', '-v', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.VERBOSE, help='verbose mode')
    xgroup.add_argument('--debug', '-d', dest='logging_level', default=argparse.SUPPRESS, action='store_const', const=logging.DEBUG, help='debug mode')
    xgroup.add_bool_argument('--progress', default=False, help='display progress bar')

    pgroup.add_argument('--device', default=Path(os.environ.get('CDROM', '/dev/cdrom')), type=_resolved_Path, help='specify alternate cdrom device')
    pgroup.add_argument('--timeout', default=0, type=int, help='timeout value (seconds)')

    app.parse_args()

    if not hasattr(app.args, 'logging_level'):
        app.args.logging_level = logging.INFO
    app.set_logging_level(app.args.logging_level)

    progress_bar = None
    if app.args.progress:
        try:
            from qip.utils import ProgressBar
        except ImportError:
            pass
        else:
            progress_bar = ProgressBar('CDROM ready?')

    try:
        return cdrom_ready(device=app.args.device,
                           timeout=app.args.timeout,
                           progress_bar=progress_bar)
    finally:
        if progress_bar:
            progress_bar.finish()


if __name__ == "__main__":
    exit(0 if main() else 1)
