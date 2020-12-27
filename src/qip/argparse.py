
import sys as _sys
import argparse as _argparse
from argparse import *

try:
    from gettext import gettext as _, ngettext
except ImportError:
    def _(message):
        return message
    def ngettext(singular,plural,n):
        if n == 1:
            return singular
        else:
            return plural

from .decorator import trace
def trace(func, **kwargs): return func

__all__ = list(_argparse.__all__) + [
    'NoExitArgumentParser',
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
        assert option_strings
        try:
            neg_option_strings = kwargs.pop('neg_option_strings')
        except KeyError:
            long_option_strings = [option_string
                                   for option_string in option_strings
                                   if len(option_string) > 1 and option_string[1] in self.prefix_chars]
            assert long_option_strings
            neg_option_strings = [
                f'{option_string[:2]}no{option_string[1]}{option_string[2:]}'
                for option_string in long_option_strings]
        assert neg_option_strings

        # if no default was supplied, use the parser-level default
        if 'default' not in kwargs:
            dest = kwargs['dest']
            if dest in self._defaults:
                kwargs['default'] = self._defaults[dest]
            elif self.argument_default is not None:
                kwargs['default'] = self.argument_default
        default = kwargs.pop('default', False)
        neg_default = SUPPRESS

        help = kwargs.pop('help', None)
        neg_help = kwargs.pop('neg_help', None)
        if help and not neg_help:
            help, neg_help = (
                _('enable {help}').format(help=help),
                _('disable {help}').format(help=help))

        action = kwargs.pop('action', 'store_true')
        action_class = self._registry_get('action', action, action)
        try:
            neg_action = kwargs.pop('neg_action')
        except KeyError:
            if issubclass(action_class, _argparse._StoreTrueAction):
                neg_action = 'store_false'
            elif issubclass(action_class, _argparse._StoreFalseAction):
                neg_action = 'store_true'
            else:
                args = {'option': option_strings[0],
                        'action': action_class}
                msg = _('unsupported action %(action)r for option string %(option)r: '
                        'provide both action and neg_action')
                raise ValueError(msg % args)
        neg_action_class = self._registry_get('action', neg_action, neg_action)

        if issubclass(neg_action_class, _argparse._StoreFalseAction) and default is False:
            default, neg_default = neg_default, default

        self.add_argument(*option_strings,
                          default=default,
                          action=action,
                          help=help,
                          **kwargs)
        self.add_argument(*neg_option_strings,
                          default=neg_default,
                          action=neg_action,
                          help=neg_help,
                          **kwargs)

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
                 add_help=True):
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

        self.register('action', 'parsers', _SubParsersAction)

    @trace
    def parse_args(self, args=None, namespace=None, process_config_file=True):
        args, argv = self.parse_known_args(args, namespace, process_config_file=process_config_file)
        if argv:
            msg = _('unrecognized arguments: %s')
            self.error(msg % ' '.join(argv))
        return args

    @trace
    def parse_known_args(self, args=None, namespace=None, process_config_file=True):
        #print('%s @ 0x%x parse_known_args(%r, %r)' % (self.__class__.__name__, id(self), args, namespace))
        if namespace is None:
            namespace = Namespace()
        if process_config_file:
            namespace = self.process_config_file_args(args, namespace)
        args, argv = super().parse_known_args(args=args, namespace=namespace)
        for k, v in args.__dict__.items():
            if isinstance(v, DefaultWrapper):
                setattr(args, k, v.inner)
        return args, argv

    @trace
    def process_config_file_args(self, args, namespace):
        #print('self._actions = %r' % (self._actions,))
        prev_actions = self._actions
        prev_option_string_actions = self._option_string_actions
        prev_defaults = self._defaults
        try:
            mock_actions = _MockActionDict()
            self._actions = [mock_actions[action] for action in prev_actions]
            self._option_string_actions = {key: mock_actions[action] for key, action in self._option_string_actions.items()}
            self._defaults = {}
            tmp_namespace = Namespace()
            if args is None:
                # args default to the system args
                tmp_args = list(_sys.argv[1:])
            else:
                # make sure that args are mutable
                tmp_args = list(args)
            tmp_namespace, tmp_args = self._parse_known_args(tmp_args, tmp_namespace)
            #print('tmp_namespace=%r' % (tmp_namespace,))
        finally:
            self._actions = prev_actions
            self._option_string_actions = prev_option_string_actions
            self._defaults = prev_defaults
        return namespace

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
                    with open(arg_string[1:], encoding='utf-8') as args_file:
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


class ParserExitException(Exception):

    def __init__(self, status, message):
        self.status = status
        self.message = message
        super().__init__(message)


class NoExitArgumentParser(ArgumentParser):

    def exit(self, status=0, message=None):
        raise ParserExitException(status, message)


class DefaultWrapper(object):

    def __init__(self, inner):
        self.inner = inner
        super().__init__()

    def __repr__(self):
        return f'{self.__class__.__name__}({self.inner!r})'
