__all__ = [
        'app',
        ]

import codecs
import configparser
import functools
import io
import logging
import os
import re
import shutil
import sys
import traceback
import urllib

from . import argparse

HAVE_ARGCOMPLETE = False
try:
    import argcomplete
    HAVE_ARGCOMPLETE = True
except ImportError:
    pass

HAVE_COLOREDLOGS = False
try:
    import coloredlogs
    HAVE_COLOREDLOGS = True
except ImportError:
    pass

DEFAULT_ROOT_LOG_FORMAT = '%(asctime)s %(name)s %(levelname)s %(message)s'
DEFAULT_APP_LOG_FORMAT = '%(asctime)s %(levelname)s %(message)s'

if HAVE_COLOREDLOGS:
    DEFAULT_LEVEL_STYLES = coloredlogs.DEFAULT_LEVEL_STYLES
    DEFAULT_LEVEL_STYLES.update(
            debug=dict(color='black', bold=coloredlogs.CAN_USE_BOLD_FONT),
            )

def addLoggingLevelName(level, levelName):
    logging.addLevelName(level, levelName)
    setattr(logging, levelName, level)

    lowerName = levelName.lower()

    def Logger_func(self, msg, *args, **kwargs):
        self.log(level, msg, *args, **kwargs)
    setattr(logging.Logger, lowerName, Logger_func)

    def LoggerAdapter_func(self, msg, *args, **kwargs):
        self.log(level, msg, *args, **kwargs)
    setattr(logging.LoggerAdapter, lowerName, LoggerAdapter_func)

    def root_func(msg, *args, **kwargs):
        logging.log(level, msg, *args, **kwargs)
    setattr(logging, lowerName, root_func)

addLoggingLevelName((logging.INFO + logging.DEBUG) // 2, "VERBOSE")

DEFAULT = object()

class App(object):

    prog = None
    descripton = None
    version = None
    contact = None

    log = logging.getLogger('__main__')

    config_parser = None
    parser = None
    args = None

    config_file_parser = None

    cache_dir = None
    _user_agent = None
    _ureg = None

    prompt_session = None
    prompt_style = None
    prompt_completer = None
    prompt_message = None

    def __init__(self):
        self.args = argparse.Namespace()
        pass

    def init(
            self,
            # parser args:
            prog=None,
            description=None,
            version=None,
            contact=None,
            # logging args:
            logging_level=None,
            ):
        if prog is None:
            prog = os.path.basename(sys.argv[0])
        self.prog = prog
        self.version = version
        self.contact = contact
        self.description = description
        self.init_encoding()
        self.init_parser()
        self.init_logging(
                level=logging_level,
                )
        self.init_terminal_size()
        self.init_prompt_toolkit()

    def init_encoding(self):
        if False:
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            e = sys.stdout.encoding
            if e is not None:
                sys.stdout = codecs.getwriter(e)(old_stdout);
                if old_stderr is old_stdout:
                    sys.stderr = sys.stdout
            if old_stderr is not old_stdout:
                e = sys.stderr.encoding
                if e is not None:
                    sys.stderr = codecs.getwriter(e)(old_stderr);

    def init_parser(self, allow_config_file=True, fromfile_prefix_chars='@',
                    **kwargs):
        description = self.description
        if self.version is not None:
            description += ' v%s' % (self.version,)
        if self.contact is not None:
            description += ' <%s>' % (self.contact,)
        if False:
            if allow_config_file and self.prog:
                if 'auto_env_var_prefix' not in kwargs:
                    kwargs['auto_env_var_prefix'] = \
                            re.sub(r'[^A-Z0-9]+', '_', self.prog.upper() + '_')
                if 'default_config_files' not in kwargs:
                    kwargs['default_config_files'] = [
                            '~/.{prog}.conf'.format(prog=self.prog)]
                if 'args_for_setting_config_path' not in kwargs:
                    kwargs['args_for_setting_config_path'] = [
                            #"-c",
                            "--config-file",
                            ]
                if 'args_for_writing_out_config_file' not in kwargs:
                    kwargs['args_for_writing_out_config_file'] = [
                            #"-w",
                            "--write-out-config-file",
                            ]

        parser_parents = []
        if allow_config_file:
            self.config_parser = argparse.ArgumentParser(
                formatter_class=argparse.ArgumentDefaultsHelpFormatter,
                description=description,
                add_help=False
                )
            self.config_parser.add_argument("--config", "-c", metavar="FILE",
                                          dest='config_file',
                                          default=argparse.DefaultStringWrapper(self.default_config_file()),
                                          type=argparse.FileType('r'),
                                          help="Specify config file")
            self.config_parser.add_argument("--no-config",
                                          default=argparse.SUPPRESS,
                                          action='store_false',
                                          help="Disable config file")
            parser_parents.append(self.config_parser)

        self.parser = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            parents=parser_parents,
            fromfile_prefix_chars=fromfile_prefix_chars,
            prog=self.prog,
            description=description,
            **kwargs)
        self.parser.version = self.version

    def init_logging(self, level=None, **kwargs):
        self.log.name = self.prog
        if HAVE_COLOREDLOGS:
            coloredlogs.install(
                    level=level,
                    fmt=DEFAULT_ROOT_LOG_FORMAT,
                    level_styles=DEFAULT_LEVEL_STYLES,
                    **kwargs)
            coloredlogs.install(
                    level=logging.NOTSET,
                    logger=self.log,
                    fmt=DEFAULT_APP_LOG_FORMAT,
                    level_styles=DEFAULT_LEVEL_STYLES,
                    )
        else:
            logging.basicConfig(
                    level=level if level is not None else logging.INFO,
                    format=DEFAULT_ROOT_LOG_FORMAT,
                    **kwargs)

    def init_terminal_size(self):
        if ('COLUMNS' not in os.environ
                or 'LINES' not in os.environ) \
                and sys.stdout.isatty():
            terminal_size = shutil.get_terminal_size()
            os.environ.setdefault('COLUMNS', str(terminal_size.columns))
            os.environ.setdefault('LINES', str(terminal_size.lines))

    def set_logging_level(self, level):
        logging.getLogger().setLevel(level)
        if HAVE_COLOREDLOGS:
            coloredlogs.set_level(level)

    def default_config_file(self):
        if not self.prog:
            return None
        config_file = None
        config_home = os.environ.get('XDG_CONFIG_HOME', None) \
            or os.path.expanduser('~/.config')
        config_file1 = f'{config_home}/{self.prog}/config'
        if os.path.exists(config_file1):
            return config_file1
        config_file2 = os.path.expanduser(f'~/.{self.prog}.conf')
        if os.path.exists(config_file2):
            return config_file2
        return config_file1  # The default that doesn't exist

    def parse_args(self, args=None, namespace=None):
        if HAVE_ARGCOMPLETE:
            argcomplete.autocomplete(self.parser)

        if args is None:
            # args default to the system args
            args = sys.argv[1:]
        else:
            # make sure that args are mutable
            args = list(args)

        remaining_args = args

        config_args = []

        if self.config_parser:
            namespace, remaining_args = self.config_parser.parse_known_args(
                args=remaining_args,
                namespace=namespace)

            if namespace.config_file \
                    and isinstance(namespace.config_file, str) \
                    and not os.path.exists(namespace.config_file):
                namespace.config_file = None
            if namespace.config_file:
                self.read_config_file(namespace.config_file)
                try:
                    options_config = self.config_file_parser["options"]
                except KeyError:
                    pass
                else:
                    for k, v in options_config.items():
                        option_string = f'--{k}'
                        action = self.parser._option_string_actions[option_string]
                        if True:
                            if action.nargs == 0:
                                assert v is None, f'{option_string} takes no argument'
                            else:
                                assert v is not None, f'{option_string} takes an argument'
                            config_args.append(option_string)
                            if v is not None:
                                config_args.append(v)
                        else:
                            argument_values = [] if v is None else [v]
                            action(self.parser, namespace, argument_values, option_string)
                if isinstance(namespace.config_file, io.IOBase):
                    namespace.config_file.close()
                    try:
                        namespace.config_file = namespace.config_file.name
                    except AttributeError:
                        namespace.config_file = None

        if config_args:
            orig_actions = self.parser._actions
            try:
                self.parser._actions = self.parser._get_optional_actions()
                namespace = self.parser.parse_args(
                    args=config_args,
                    namespace=namespace)
            finally:
                self.parser._actions = orig_actions

        namespace = self.parser.parse_args(
            args=remaining_args,
            namespace=namespace)

        self.args = namespace

        nice = getattr(self.args, 'nice', None)
        if nice is not None:
            import qip.exec
            qip.exec.renice(pid=os.getpid(),
                            priority=nice)

        ionice = getattr(self.args, 'ionice', None)
        if ionice is not None:
            import qip.exec
            qip.exec.ionice(pid=os.getpid(),
                            _class=2,  # best-effort
                            classdata=ionice)

        return self.args

    def read_config_file(self, config_file):
        self.config_file_parser = configparser.ConfigParser(allow_no_value=True)
        if isinstance(config_file, io.IOBase):
            self.config_file_parser.read_file(config_file)
        elif isinstance(config_file, str):
            self.config_file_parser.read([str(config_file)])
        else:
            raise TypeError(config_file)

    @property
    def user_agent(self):
        user_agent = self._user_agent
        if user_agent is None:
            if self.prog:
                user_agent = '{}'.format(self.prog)
                if self.version is not None:
                    user_agent += '/{}'.format(self.version)
                if self.contact is not None:
                    user_agent += ' ({})'.format(self.contact)
        return user_agent

    @user_agent.setter
    def user_agent(self, value):
        self._user_agent = value

    @property
    def ureg(self):
        '''See: https://pint.readthedocs.org'''
        ureg = self._ureg
        if ureg is None:
            from pint import UnitRegistry
            self._ureg = ureg = UnitRegistry()
            from . import json
            json.register_class_alias(ureg.Quantity, 'pint:Quantity')
            json.register_class(ureg.Quantity, ureg.Quantity.to_tuple, ureg.Quantity.from_tuple)
        return ureg

    def mk_cache_file(self, cache_token):
        cache_dir = self.cache_dir
        if not cache_dir:
            return None
        os.makedirs(cache_dir, exist_ok=True)
        cache_file = os.path.join(
            cache_dir,
            urllib.parse.quote(cache_token, safe=''))
        return cache_file

    def main_wrapper(self, func):
        @functools.wraps(func)
        def wrapper():
            try:
                ret = func()
            except Exception as e:
                self.log.error("%s: %s", e.__class__.__name__, e)
                if self.log.isEnabledFor(logging.DEBUG):
                    etype, value, tb = sys.exc_info()
                    self.log.debug(''.join(traceback.format_exception(etype, value, tb)))
                app.exit(1)
            if ret is True or ret is None:
                app.exit(0)
            elif ret is False:
                app.exit(1)
            else:
                app.exit(ret)
        return wrapper

    def exit(self, ret):
        if getattr(self.args, 'beep', False):
            import qip.utils
            qip.utils.beep()
        exit(ret)

    def init_prompt_toolkit(self):
        pass

    def get_prompt_message(self):
        return [
            ('class:app', self.prog or ''),
            ('class:cue', '> '),
        ]

    def init_prompt_session(self):
        if self.prompt_session is None:

            self.prompt_message = self.get_prompt_message

            from prompt_toolkit import PromptSession
            self.prompt_session = PromptSession(
                enable_suspend=True,
            )

            from prompt_toolkit.styles import Style
            self.prompt_style = Style.from_dict({
                '': '#ffffff',
                'app': '#884444',
                'cue': '#00aa00',
                'field': '#884444',
                'error': '#ff0000 underline',
            })

    def prompt(self, message=None, *, style=None, completer=None, beep=DEFAULT):
        if beep is DEFAULT:
            beep = getattr(app.args, 'beep', False) and getattr(app.args, 'interactive', False)
        if beep:
            import qip.utils
            qip.utils.beep()
        self.init_prompt_session()
        c = self.prompt_session.prompt(
            message=None if message is False else (message or self.prompt_message),
            style=None if style is False else (style or self.prompt_style),
            completer=None if completer is False else (completer or self.prompt_completer),
        )
        return c

    def input_dialog(self, title='', text='', initial_text='', ok_text='OK', cancel_text='Cancel',
                     completer=None, password=False, style=None, async_=False):
        """
        Display a text input box.
        Return the given text, or None when cancelled.

        Custom init_dialog:
          - Support initial_text
        """

        from prompt_toolkit.application.current import get_app
        from prompt_toolkit.layout.containers import HSplit
        from prompt_toolkit.layout.dimension import Dimension as D
        from prompt_toolkit.widgets import (
            Button,
            TextArea,
            Dialog,
            Label,
        )
        from prompt_toolkit.shortcuts.dialogs import (
            _run_dialog,
            _return_none,
        )

        def accept(buf):
            get_app().layout.focus(ok_button)
            return True  # Keep text.

        def ok_handler():
            get_app().exit(result=textfield.text)

        ok_button = Button(text=ok_text, handler=ok_handler)
        cancel_button = Button(text=cancel_text, handler=_return_none)

        textfield = TextArea(
            text=initial_text,
            multiline=False,
            password=password,
            completer=completer,
            accept_handler=accept)

        dialog = Dialog(
            title=title,
            body=HSplit([
                Label(text=text, dont_extend_height=True),
                textfield,
            ], padding=D(preferred=1, max=1)),
            buttons=[ok_button, cancel_button],
            with_background=True)

        return _run_dialog(dialog,
                           style=None if style is False else (style or self.prompt_style),
                           async_=async_)

    def print(self, *args, style=DEFAULT, **kwargs):
        self.init_prompt_session()
        from prompt_toolkit import print_formatted_text
        return print_formatted_text(
            *args, **kwargs,
            style=self.prompt_style if style is DEFAULT else style,
        )

app = App()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
