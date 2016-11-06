__all__ = [
        'app',
        ]

from . import argparse
import re
import logging
import os
import sys
import argcomplete

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

class App(object):

    log = logging.getLogger('__main__')
    parser = None
    prog = None
    descripton = None
    version = None
    contact = None
    _user_agent = None
    _ureg = None

    def __init__(self):
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
        self.init_parser()
        self.init_logging(
                level=logging_level,
                )

    def init_parser(self, allow_config_file=True, **kwargs):
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
        self.parser = argparse.ArgumentParser(
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

    def set_logging_level(self, level):
        if HAVE_COLOREDLOGS:
            coloredlogs.set_level(level)
        else:
            logging.getLogger().setLevel(level)

    def parse_args(self, **kwargs):
        argcomplete.autocomplete(self.parser)
        self.args = self.parser.parse_args(**kwargs)
        return self.args

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

app = App()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
