# Based on ocode.c from the original lsdvd:
#     lsdvd 0.18 - GPL Copyright (c) 2002-2005, 2014 "Written" by Chris Phillips <acid_kewpie@users.sf.net>

__all__ = (
    'debug_syntax',
    'perl_syntax',
    'python_syntax',
    'ruby_syntax',
    'xml_syntax',
)

import collections
import contextlib
import sys
import logging
log = logging.getLogger(__name__)

class Syntax(collections.namedtuple('Syntax', (
        'indent',
        'head',
        'start',
        'defn',
        'defn_sep',
        'hash_outer',
        'hash_inner',
        'hash_anon',
        'array_outer',
        'array_inner',
        'adef_sep',
        'return_hash_outer',
        'return_array_outer',
        'return_hash_inner',
        'return_array_inner',
        'stop',
))):

    def Formatter(self, /, *args, **kwargs):
        return Formatter(syntax=self, *args, **kwargs)

# This syntax table is not used, but is helpful as a debugging aid.
debug_syntax = Syntax(
    head="<head/>",
    start="<start-{name}/>",
    indent="<indent/>",
    defn="<defn>%s</defn>",
    defn_sep="<defn_sep/>",
    hash_outer="<hash_outer>{name}</hash_outer>",
    hash_inner="<hash_inner>{name}</hash_inner>",
    hash_anon="<hash_anon/>",
    array_outer="<array_outer>{name}</array_outer>",
    array_inner="<array_inner>{name}</array_inner>",
    adef_sep="<adef_sep/>",
    return_hash_outer="</return_hash_outer>",
    return_array_outer="</return_array_outer>",
    return_hash_inner="</return_hash_inner>",
    return_array_inner="</return_array_inner>{name}",
    stop="<stop-{name}/>",
)

perl_syntax = Syntax(
    head=None,
    start="our %%{name} = (\n",
    indent="  ",
    defn="%s => ",
    defn_sep=",\n",
    hash_outer="our %%{name} = (\n",
    return_hash_outer=");\n",
    hash_inner="{name} => {{\n",
    return_hash_inner="}},\n",
    hash_anon="}}\n",
    array_outer="our @{name} = (\n",
    return_array_outer=");\n",
    array_inner="{name} => [\n",
    return_array_inner="],\n",
    adef_sep=",\n",
    stop=");\n",
)

python_syntax = Syntax(
    head=None,
    start="{name} = {{\n",
    indent="  ",
    defn="'%s' : ",
    defn_sep=",\n",
    hash_outer="{name} = {{\n",
    return_hash_outer="}}\n",
    hash_inner="'{name}' : {{\n",
    return_hash_inner="}},\n",
    hash_anon="{{\n",
    array_outer="{name} = [\n",
    return_array_outer="]\n",
    array_inner="'{name}' : [\n",
    return_array_inner="],\n",
    adef_sep=",\n",
    stop="}}\n",
)

# This syntax table is not used, but is included here as a starting point
# for somebody who understands Ruby syntax.  For the values that I am not
# certain of, I left some xml-like values.
ruby_syntax = Syntax(
    head=None,
    start="{{\n",
    indent="  ",
    defn=":%s => ",
    defn_sep=",\n",
    hash_outer="{{\n",
    return_hash_outer="}}\n",
    hash_inner="<hash_inner>{name}</hash_inner>",
    return_hash_inner="}},\n",
    hash_anon="{{\n",
    array_outer="<array_outer>{name}</array_outer>",
    return_array_outer="<return_array_outer/>",
    array_inner=":{name} => [",
    return_array_inner="],\n",
    adef_sep=",\n",
    stop="}}\n",
)

xml_syntax = Syntax(
    head="<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n",
    start="<{name}>\n",
    indent="<indent/>",
    defn="<defn>%s</defn>",
    defn_sep="<defn_sep/>",
    hash_outer="<{name}>\n",
    return_hash_outer="</{name}>\n",
    hash_inner="<{name}>\n",
    return_hash_inner="</{name}>\n",
    hash_anon=None,
    array_outer="<{name}>\n",
    return_array_outer="</{name}>\n",
    array_inner="<{name}>\n",
    return_array_inner="</{name}>\n",
    adef_sep="<adef_sep/>",
    stop="</{name}>\n",
)

class Formatter(object):

    syntax = None
    lvl = None
    file = None

    def __init__(self, /, syntax, file=None):
        self.syntax = syntax
        self.lvl = 0
        self.file = file

    def printf(self, /, fmt, *args, **kwargs):
        if fmt is not None:
            try:
                print(fmt.format(**kwargs) % args,
                      end='',
                      file=self.file or sys.stdout,
                      )
            except Exception as e:
                log.debug('fmt=%r, args=%r, kwargs=%r, file=%r, e=%r',
                          fmt, args, kwargs, self.file, e)
                raise

    def INDENT(self, /):
        if self.syntax.indent is not None:
            self.printf(self.syntax.indent * self.lvl)

    @contextlib.contextmanager
    def generic_indent_context(self, /,
                               format_open, format_close, *,
                               lvl_inc=1,
                               **kwargs):
        self.INDENT()
        self.printf(format_open, **kwargs)
        self.lvl += lvl_inc
        try:
            yield
        finally:
            self.lvl -= lvl_inc
        self.INDENT()
        self.printf(format_close, **kwargs)

    #@contextlib.contextmanager
    def START(self, /, name):
        self.INDENT()
        self.printf(self.syntax.head, name=name)
        return self.generic_indent_context(
            self.syntax.start,
            self.syntax.stop,
            lvl_inc=1 if self.syntax.start else 0,
            name=name)

    def DEF(self, /, name, format, *args):
        self.INDENT()
        self.printf(self.syntax.defn, name)
        self.printf(format, *args)
        self.printf(self.syntax.defn_sep)

    #@contextlib.contextmanager
    def HASH(self, /, name):
        if self.lvl:
            format_open = self.syntax.hash_inner
            format_close = self.syntax.return_hash_inner
        else:
            format_open = self.syntax.hash_outer
            format_close = self.syntax.return_hash_outer
        if name is None:
            format_open = self.syntax.hash_anon
        return self.generic_indent_context(
            format_open,
            format_close,
            name=name)

    #@contextlib.contextmanager
    def ARRAY(self, /, name):
        if self.lvl:
            format_open = self.syntax.array_inner
            format_close = self.syntax.return_array_inner
        else:
            format_open = self.syntax.array_outer
            format_close = self.syntax.return_array_outer
        return self.generic_indent_context(
            format_open,
            format_close,
            name=name)

    def ADEF(self, /, format, *args):
        self.INDENT()
        self.printf(format, *args)
        self.printf(self.syntax.adef_sep)

