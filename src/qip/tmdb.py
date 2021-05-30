"""The Movie DB API Access

See: https://developers.themoviedb.org/3/getting-started/introduction
"""

__all__ = [
]

from pathlib import Path
import configparser
import io
import os
import tmdbv3api
from tmdbv3api import *

from .isolang import isolang

class TMDb(tmdbv3api.TMDb):

    @staticmethod
    def default_config_file():
        config_file = None
        config_home = os.environ.get('XDG_CONFIG_HOME', None)
        config_home = Path(config_home) if config_home else Path.home() / '.config'
        config_file1 = config_home / 'tmdb/config'
        if config_file1.exists():
            return config_file1
        config_file2 = Path.home() / '.tmdb.conf'
        if config_file2.exists():
            return config_file2
        return config_file1  # The default that doesn't exist

    config_file_parser = None

    def __init__(self, *,
                 apikey=None,
                 config_file=None,
                 interactive=None,  # TODO
                 debug=False,
                 language=None,
                 **kwargs):

        config_file = config_file or self.default_config_file()
        self.config_file_parser = configparser.ConfigParser(allow_no_value=True)
        if isinstance(config_file, io.IOBase):
            self.config_file_parser.read_file(config_file)
        elif isinstance(config_file, (str, os.PathLike)):
            self.config_file_parser.read([os.fspath(config_file)])
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

        super().__init__(**kwargs)

        # tvdb_api.Tvdb requires all 3 variables to be set so fill them manually instead
        if apikey is not None:
            self.api_key = apikey
        if language is not None:
            self.language = language
        if debug is not None:
            self.debug = debug or ''  # TMDb returns bool(env_str)

    @property
    def language(self):
        return os.environ.get(self.TMDB_LANGUAGE)

    @language.setter
    def language(self, language):
        if language is None:
            os.environ.pop(self.TMDB_LANGUAGE, None)
        else:
            os.environ[self.TMDB_LANGUAGE] = isolang(language).iso639_1

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
