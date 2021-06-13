# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import sys as _sys
import argparse as _argparse
from argparse import *

#from .decorator import trace
def trace(func, **kwargs): return func

from .utils import Constants as _Constants
Auto = _Constants.Auto
Ask = _Constants.Ask
NotSet = _Constants.NotSet

__all__ = list(_argparse.__all__) + [
    'ParserExitException',
]

class _AttributeHolder(_argparse._AttributeHolder):
    pass

class HelpFormatter(_argparse.HelpFormatter):
    pass

class RawDescriptionHelpFormatter(_argparse.RawDescriptionHelpFormatter, HelpFormatter):
    pass

class RawTextHelpFormatter(_argparse.RawTextHelpFormatter, RawDescriptionHelpFormatter):
    pass

class ArgumentDefaultsHelpFormatter(_argparse.ArgumentDefaultsHelpFormatter, HelpFormatter):

    def _get_help_string(self, action):
        help = action.help
        if '%(default)' not in action.help:
            if action.default is not SUPPRESS:
                defaulting_nargs = [OPTIONAL, ZERO_OR_MORE]
                if action.option_strings or action.nargs in defaulting_nargs:
                    if isinstance(action, _argparse._StoreTrueAction) and action.default is True:
                        return help + ' (default)'
                    elif isinstance(action, _argparse._StoreFalseAction) and action.default is False:
                        return help + ' (default)'
        return super()._get_help_string(action)

class MetavarTypeHelpFormatter(_argparse.MetavarTypeHelpFormatter, HelpFormatter):
    pass

class RawDescriptionArgumentDefaultsHelpFormatter(RawDescriptionHelpFormatter, ArgumentDefaultsHelpFormatter):
    pass

class RawTextArgumentDefaultsHelpFormatter(RawTextHelpFormatter, ArgumentDefaultsHelpFormatter):
    pass

#class ArgumentError(Exception): pass

#class ArgumentTypeError(Exception): pass

class _ActionMeta(type):

    def __new__(mcs, name, bases, dct):
        if '__call__' in dct:
            dct['__call__'] = trace(dct['__call__'], pout=False)
        cls = super().__new__(mcs, name, bases, dct)
        return cls

class Action(_argparse.Action, _AttributeHolder, metaclass=_ActionMeta):

    def __call__(self, *args, **kwargs):
        return super().__call__(*args, **kwargs)

#class _StoreAction(Action): pass
#class _StoreConstAction(Action): pass
#class _StoreTrueAction(_StoreConstAction): pass
#class _StoreFalseAction(_StoreConstAction): pass
#class _AppendAction(Action): pass
#class _AppendConstAction(Action): pass
#class _CountAction(Action): pass
#class _HelpAction(Action): pass
#class _VersionAction(Action): pass
#class _SubParsersAction(Action): pass
#class FileType(object): pass

def constants_parser(value):
    value = _Constants._value2member_map_.get(value, value)
    return value

def constants_type(value):
    try:
        value = _Constants._value2member_map_[value]
    except KeyError:
        raise ValueError(value)
    return value

class _StoreBoolOrSuperAction(Action):

    def __init__(self, *, choices, type=None, nargs=None, **kwargs):
        super().__init__(**kwargs)
        self.choices = choices
        self.type = type
        self.nargs = nargs

    def __call__(self, parser, namespace, values, option_string=None):
        if values is True or values == []:
            return super().__call__(parser=parser,
                                    namespace=namespace,
                                    values=values,
                                    option_string=option_string)
        else:
            setattr(namespace, self.dest, values)

class _StoreConstOrSuperAction(_StoreBoolOrSuperAction, _argparse._StoreConstAction):

    pass

class _StoreTrueOrSuperAction(_StoreBoolOrSuperAction, _argparse._StoreTrueAction):

    pass

class _StoreFalseOrSuperAction(_StoreBoolOrSuperAction, _argparse._StoreFalseAction):

    pass

class ConfigFileAction(Action):
    pass

class _NamespaceMeta(type):

    def __new__(mcs, name, bases, dct):
        if '__setattr__' in dct:
            dct['__setattr__'] = trace(dct['__setattr__'], pout=False)
        cls = super().__new__(mcs, name, bases, dct)
        return cls

class Namespace(_argparse.Namespace, _AttributeHolder, metaclass=_NamespaceMeta):

    def __setattr__(self, name, value):
        return super().__setattr__(name, value)

    #def __repr__(self):
    #    return '<{}>'.format(self.__class__.__name__)

class _ActionsContainer(_argparse._ActionsContainer):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # register actions
        self.register('action', 'store_const_or_super', _StoreConstOrSuperAction)
        self.register('action', 'store_true_or_super', _StoreTrueOrSuperAction)
        self.register('action', 'store_false_or_super', _StoreFalseOrSuperAction)

    def add_argument_group(self, *args, **kwargs):
        group = _ArgumentGroup(self, *args, **kwargs)
        self._action_groups.append(group)
        return group

    def add_mutually_exclusive_group(self, **kwargs):
        group = _MutuallyExclusiveGroup(self, **kwargs)
        self._mutually_exclusive_groups.append(group)
        return group

    def add_bool_argument(self, *args, **kwargs):

        kwargs = self._get_optional_kwargs(*args, **kwargs)

        option_strings = kwargs.pop('option_strings')
        assert option_strings, f'Invalid option_strings: {option_strings}'
        try:
            neg_option_strings = kwargs.pop('neg_option_strings')
        except KeyError:
            long_option_strings = [option_string
                                   for option_string in option_strings
                                   if len(option_string) > 1 and option_string[1] in self.prefix_chars]
            assert long_option_strings, f'Invalid long_option_strings: {long_option_strings}'
            neg_option_strings = [
                f'{option_string[:2]}no{option_string[1]}{option_string[2:]}'
                for option_string in long_option_strings]
        assert neg_option_strings, f'Invalid neg_option_strings: {neg_option_strings}'

        help = kwargs.pop('help', None)
        neg_help = kwargs.pop('neg_help', None)
        if help and not neg_help:
            if help.startswith('enable '):
                help, neg_help = (
                    f'{help}',
                    f'disable {help[7:]}')
            elif help.startswith('do not '):
                help, neg_help = (
                    f'{help}',
                    f'{help[7:]}')
            else:
                help, neg_help = (
                    f'{help}',
                    f'do not {help}')

        pos_kwargs2 = {}
        neg_kwargs2 = {}

        # keyword arguments that only apply to positive option
        for k in ('type', 'nargs', 'choices', 'const'):
            try:
                pos_kwargs2[k] = kwargs.pop(k)
            except KeyError:
                pass

        has_choices = bool(pos_kwargs2.get('choices', None))
        if has_choices:
            pos_kwargs2.setdefault('nargs', OPTIONAL)

        is_list = pos_kwargs2.get('nargs', None) not in (None, OPTIONAL)
        is_optional = pos_kwargs2.get('nargs', None) in (OPTIONAL, ZERO_OR_MORE)

        try:
            action = kwargs.pop('action')
        except KeyError:
            if is_list or 'const' in pos_kwargs2:
                action = 'store_const'
                pos_kwargs2.setdefault('const', [True] if is_list else True)
            else:
                action = 'store_true'

        if has_choices:
            if action in ('store_const', 'store_true', 'store_false'):
                action += '_or_super'

        if pos_kwargs2.get('nargs', None) is not None:
            pos_kwargs2.setdefault('type', constants_parser)

        # if no default was supplied, use the parser-level default
        try:
            default = kwargs.pop('default')
        except KeyError:
            dest = kwargs['dest']
            if dest in self._defaults:
                default = self._defaults[dest]
            elif self.argument_default is not None:
                default = self.argument_default
            else:
                default = [False] if is_list else False
        neg_default = SUPPRESS

        action_class = self._registry_get('action', action, action)
        try:
            neg_action = kwargs.pop('neg_action')
        except KeyError:
            if issubclass(action_class, _argparse._StoreTrueAction):
                neg_action = 'store_false'
            elif issubclass(action_class, _argparse._StoreFalseAction):
                neg_action = 'store_true'
            elif issubclass(action_class, _argparse._StoreConstAction) and pos_kwargs2['const'] is True:
                neg_action = 'store_const'
                neg_kwargs2['const'] = False
            elif issubclass(action_class, _argparse._StoreConstAction) and pos_kwargs2['const'] is False:
                neg_action = 'store_const'
                neg_kwargs2['const'] = True
            elif issubclass(action_class, _argparse._StoreConstAction) and pos_kwargs2['const'] == [True]:
                neg_action = 'store_const'
                neg_kwargs2['const'] = [False]
            elif issubclass(action_class, _argparse._StoreConstAction) and pos_kwargs2['const'] == [False]:
                neg_action = 'store_const'
                neg_kwargs2['const'] = [True]
            else:
                args = {'option': option_strings[0],
                        'action': action_class}
                msg = 'unsupported action %(action)r for option string %(option)r: provide both action and neg_action'
                raise ValueError(msg % args)
        neg_action_class = self._registry_get('action', neg_action, neg_action)

        if issubclass(neg_action_class, _argparse._StoreFalseAction) and default is False:
            default, neg_default = neg_default, default

        pos_kwargs2.update(kwargs)
        neg_kwargs2.update(kwargs)

        self.add_argument(*option_strings,
                          default=default,
                          action=action,
                          help=help,
                          **pos_kwargs2)
        self.add_argument(*neg_option_strings,
                          default=neg_default,
                          action=neg_action,
                          help=neg_help,
                          **neg_kwargs2)

class _ArgumentGroup(_argparse._ArgumentGroup, _ActionsContainer):

    def add_argument(self, *args, **kwargs):
        if 'metavar' not in kwargs:
            if kwargs.get('type', None) is int:
                choices = kwargs.get('choices', None)
                if isinstance(choices, range):
                    kwargs['metavar'] = f'[{choices[0]}-{choices[-1]}]'
        return super().add_argument(*args, **kwargs)

class _MutuallyExclusiveGroup(_argparse._MutuallyExclusiveGroup, _ArgumentGroup):
    pass

class _MockAction(object):

    default = SUPPRESS
    required = False
    dest = SUPPRESS

    def __init__(self, orig_action):
        self._orig_action = orig_action

    def __call__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        return getattr(self._orig_action, name)

    def __setattr__(self, name, value):
        if name != '_orig_action':
            raise AttributeError(name)
        super().__setattr__(name, value)

class _MockActionDict(dict):

    def __missing__(self, key):
        if isinstance(key, ConfigFileAction):
            value = key
        else:
            value = _MockAction(key)
        self[key] = value
        return value

class _SubParsersAction(_argparse._SubParsersAction):

    def add_parser(self, name, **kwargs):
        parser = super().add_parser(name=name, **kwargs)
        parser.parser_name = name
        return parser

    def __call__(self, parser, namespace, values, option_string=None):
        parser_name = values[0]
        arg_strings = values[1:]

        # select the subparser
        try:
            subparser = self._name_parser_map[parser_name]
        except KeyError:
            pass
        else:
            # Replace aliases with their original parser name
            try:
                parser_name = subparser.parser_name
            except AttributeError:
                pass
            else:
                values = [parser_name] + arg_strings

        super().__call__(parser=parser, namespace=namespace, values=values,
                         option_string=option_string)

class ArgumentParser(_argparse.ArgumentParser, _AttributeHolder, _ActionsContainer):

    def __init__(self,
                 prog=None,
                 usage=None,
                 description=None,
                 epilog=None,
                 parents=[],
                 formatter_class=HelpFormatter,
                 prefix_chars='-',
                 fromfile_prefix_chars=None,
                 argument_default=None,
                 conflict_handler='error',
                 add_help=True,
                 exit_on_error=True):
        super().__init__(
            prog=prog,
            usage=usage,
            description=description,
            epilog=epilog,
            parents=parents,
            formatter_class=formatter_class,
            prefix_chars=prefix_chars,
            fromfile_prefix_chars=fromfile_prefix_chars,
            argument_default=argument_default,
            conflict_handler=conflict_handler,
            add_help=add_help)
        self.exit_on_error = exit_on_error  # 3.9 feature

        self.register('action', 'parsers', _SubParsersAction)

    def exit(self, status=0, message=None):
        if self.exit_on_error:  # 3.9 is not supposed to call exit, but it can.
            super().exit(status=status, message=message)
        else:
            raise ParserExitException(status=status, message=message.rstrip())

    @trace
    def parse_args(self, args=None, namespace=None):
        args, argv = self.parse_known_args(args, namespace)
        if argv:
            msg = 'unrecognized arguments: %s'
            self.error(msg % ' '.join(argv))
        return args

    @trace
    def parse_known_args(self, args=None, namespace=None):
        if namespace is None:
            namespace = Namespace()
        args, argv = super().parse_known_args(args=args, namespace=namespace)
        for k, v in args.__dict__.items():
            if isinstance(v, DefaultWrapper):
                setattr(args, k, v.inner)
        return args, argv

    def _read_args_from_files(self, arg_strings):
        # expand arguments referencing files
        new_arg_strings = []
        for arg_string in arg_strings:

            # for regular arguments, just add them back into the list
            if not arg_string or arg_string[0] not in self.fromfile_prefix_chars:
                new_arg_strings.append(arg_string)

            # replace arguments referencing files with the file content
            else:
                try:
                    with open(arg_string[1:], encoding='utf-8-sig') as args_file:
                        arg_strings = []
                        for arg_line in args_file.read().splitlines():
                            for arg in self.convert_arg_line_to_args(arg_line):
                                arg_strings.append(arg)
                        arg_strings = self._read_args_from_files(arg_strings)
                        new_arg_strings.extend(arg_strings)
                except OSError:
                    err = _sys.exc_info()[1]
                    self.error(str(err))

        # return the modified argument list
        return new_arg_strings

    def _get_value(self, action, arg_string):
        try:
            return super()._get_value(action, arg_string)
        except ArgumentError:
            type_func = self._registry_get('type', action.type, action.type)
            msg = getattr(type_func, 'ArgumentError_msg', None)
            if msg:
                raise ArgumentError(action, msg % {
                    'value': arg_string,
                })
            raise


class ParserExitException(ArgumentError):

    def __init__(self, status, message):
        self.status = status
        super().__init__(argument=None, message=message)

    def __str__(self):
        return self.message


class DefaultWrapper(object):

    def __init__(self, inner):
        self.inner = inner
        super().__init__()

    def __repr__(self):
        return f'{self.__class__.__name__}({self.inner!r})'

    def __str__(self):
        return str(self.inner)
