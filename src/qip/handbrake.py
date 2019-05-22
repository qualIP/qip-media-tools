
__all__ = [
        'HandBrake',
        ]

import re
import logging
log = logging.getLogger(__name__)

from .exec import *
from .parser import *
from qip.utils import byte_decode
from qip import json

class CHandBrake(Executable):

    name = 'HandBrakeCLI'

    run_func = staticmethod(do_spawn_cmd)

    @classmethod
    def kwargs_to_cmdargs(cls, **kwargs):
        return Executable.kwargs_to_cmdargs_gnu_getopt(
            {k.replace('_', '-'): v
             for k, v in kwargs.items()})

    def parse_json_output(self, out, sections={'JSON Title Set'}, load=True):
        out = byte_decode(out)
        parser = lines_parser(out.split('\n'))
        while parser.advance():
            if parser.line == '':
                continue
            m = re.match(r'^([A-Z][A-Za-z ]*): ({)$', parser.line)
            if m:
                this_section = m.group(1)
                this_content = [m.group(2)]
                while parser.advance():
                    this_content.append(parser.line)
                    if parser.line == '}':
                        break
                else:
                    raise ValueError('End of section %r not found.' % (this_section,))
                if sections is None or this_section in sections:
                    yield (this_section,
                           json.loads('\n'.join(this_content)) if load \
                           else '\n'.join(this_content))
            else:
                raise ValueError('Expected section heading: %r' % (parser.line,))

HandBrake = CHandBrake()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
