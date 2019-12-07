"""TheTVDB API Access

See: https://api.thetvdb.com/swagger

Attribution: TV information and images are provided by TheTVDB.com, but we are not endorsed or certified by TheTVDB.com or its affiliates.
"""

__all__ = [
]

import configparser
import io
import os
import tvdb_api

from .isolang import isolang

class Tvdb(tvdb_api.Tvdb):

    @staticmethod
    def default_config_file():
        config_file = None
        config_home = os.environ.get('XDG_CONFIG_HOME', None) \
            or os.path.expanduser('~/.config')
        config_file1 = f'{config_home}/thetvdb/config'
        if os.path.exists(config_file1):
            return config_file1
        config_file2 = os.path.expanduser(f'~/.thetvdb.conf')
        if os.path.exists(config_file2):
            return config_file2
        return config_file1  # The default that doesn't exist

    config_file_parser = None

    def __init__(self, *,
                 apikey=None,
                 username=None,
                 userkey=None,
                 config_file=None,
                 language=None,
                 **kwargs):

        config_file = config_file or self.default_config_file()
        self.config_file_parser = configparser.ConfigParser(allow_no_value=True)
        if isinstance(config_file, io.IOBase):
            self.config_file_parser.read_file(config_file)
        elif isinstance(config_file, str):
            self.config_file_parser.read([str(config_file)])
        else:
            raise TypeError(config_file)

        try:
            auth_config = self.config_file_parser['auth']
        except KeyError:
            pass
        else:
            try:
                apikey = apikey or auth_config['apikey']
            except KeyError:
                pass
            try:
                username = username or auth_config['username']
            except KeyError:
                pass
            try:
                userkey = userkey or auth_config['userkey']
            except KeyError:
                pass

        language = 'en' if language is None else isolang(language).iso639_1

        super().__init__(**kwargs)

        # tvdb_api.Tvdb requires all 3 variables to be set so fill them manually instead
        self.config['auth_payload']['apikey'] = apikey
        self.config['auth_payload']['username'] = username
        self.config['auth_payload']['userkey'] = userkey

    @property
    def language(self):
        return self.config['language']

    @language.setter
    def language(self, value):
        self.config['language'] = 'en' if language is None else isolang(language).iso639_1

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
