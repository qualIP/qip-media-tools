# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
        'lines_parser',
        ]

import collections.abc
import itertools
import re

class lines_parser(object):

    lines_iter = None

    match = None
    line = None
    line_no = 0
    next_line_no = 1

    def __init__(self, lines):
        self.lines_iter = lines if isinstance(lines, collections.abc.Iterator) else iter(lines)

    def advance(self):
        try:
            self.line = next(self.lines_iter)
            self.line_no = self.next_line_no
            self.next_line_no += 1
        except StopIteration:
            self.line = None
            return False
        return True

    def pushback(self, line):
        self.lines_iter = itertools.chain([line], self.lines_iter)
        self.next_line_no -= 1

    def re_search(self, pattern, **kwargs):
        self.match = re.search(pattern, self.line, **kwargs)
        return self.match

    def re_match(self, pattern, **kwargs):
        self.match = re.match(pattern, self.line, **kwargs)
        return self.match

    def __iter__(self):
        while self.advance():
            yield self.line

    def raiseValueError(self, message=None, input=None, prefix=None):
        message = message or 'Invalid line: {line!r}'
        prefix = prefix or ('{input}:{line_no}: ' if input else '{input}:{line_no}: ')
        message = message.format(
            input=input,
            line=self.line,
            line_no=self.line_no,
        )
        prefix = prefix.format(
            input=input,
            line=self.line,
            line_no=self.line_no,
        )
        raise ValueError(prefix + message)
