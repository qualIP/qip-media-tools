# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

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
from .xdg import XdgResource
from .propex import propex


class TMDb(tmdbv3api.TMDb, XdgResource):

    xdg_resource = 'tmdb'

    def default_config_file(self):
        config_file1 = self.save_config_path() / 'config'
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

    movie_genre_list = propex(
        name='movie_genre_list',
    )

    @movie_genre_list.initter
    def movie_genre_list(self):
        genre = Genre()
        return genre.movie_list()

    movie_genre_map = propex(
        name='movie_genre_map',
    )

    @movie_genre_map.initter
    def movie_genre_map(self):
        return {
            genre.id: genre
            for genre in self.movie_genre_list
        }

    tvshow_genre_list = propex(
        name='tvshow_genre_list',
        )

    @tvshow_genre_list.initter
    def tvshow_genre_list(self):
        genre = Genre()
        return genre.tv_list()

    def movie_to_tags(self, o_movie):
        #app.log.debug('o_movie=%r:\n%s', o_movie, pprint.pformat(vars(o_movie)))
        #{'adult': False,
        # 'backdrop_path': '/eHUoB8NbvrvKp7KQMNgvc7yLpzM.jpg',
        # 'entries': {'adult': False,
        #             'backdrop_path': '/eHUoB8NbvrvKp7KQMNgvc7yLpzM.jpg',
        #             'genre_ids': [12, 18, 53],
        #             'id': 44115,
        #             'original_language': 'en',
        #             'original_title': '127 Hours',
        #             'overview': "The true story of mountain climber Aron Ralston's "
        #                         'remarkable adventure to save himself after a fallen '
        #                         'boulder crashes on his arm and traps him in an '
        #                         'isolated canyon in Utah.',
        #             'popularity': 11.822,
        #             'poster_path': '/c6Nu7UjhGCQtV16WXabqOQfikK6.jpg',
        #             'release_date': '2010-11-05',
        #             'title': '127 Hours',
        #             'video': False,
        #             'vote_average': 7,
        #             'vote_count': 4828},
        # 'genre_ids': [12, 18, 53],
        # 'id': 44115,
        # 'original_language': 'en',
        # 'original_title': '127 Hours',
        # 'overview': "The true story of mountain climber Aron Ralston's remarkable "
        #             'adventure to save himself after a fallen boulder crashes on his '
        #             'arm and traps him in an isolated canyon in Utah.',
        # 'popularity': 11.822,
        # 'poster_path': '/c6Nu7UjhGCQtV16WXabqOQfikK6.jpg',
        # 'release_date': '2010-11-05',
        # 'title': '127 Hours',
        # 'video': False,
        # 'vote_average': 7,
        # 'vote_count': 4828}
        from qip.mm import AlbumTags, ITunesXid
        movie_api = Movie()
        tags = AlbumTags()
        # tags.contenttype = 'movie'  # Could also be 'tvshow'
        tags.tmdb_id = f'movie/{o_movie.id}'
        tags.title = o_movie.title
        try:
            tags.originaltitle = o_movie.original_title
        except AttributeError:
            pass
        try:
            tags.date = o_movie.release_date
        except AttributeError:
            pass
        try:
            tags.description = o_movie.overview
        except AttributeError:
            pass
        try:
            if o_movie.adult:
                tags.contentrating = 'explicit'
        except AttributeError:
            pass
        try:
            if o_movie.video:
                tags.contenttype = 'video'
        except AttributeError:
            pass
        genres = self.movie_to_genres(o_movie)
        if genres:
            tags.genres = (genre.name for genre in genres)
        writers = []
        screenplay_writers = []
        credits = movie_api.credits(o_movie.id)
        for person in credits.get('crew', ()):
            person.setdefault('department', None)
            if person.department == 'Writing':
                person.setdefault('job', None)
                if person.job == 'Writer':
                    writers.append(person)
                elif person.job == 'Screenplay':
                    screenplay_writers.append(person)
        if writers:
            tags.artist = [person.name for person in writers]
        elif screenplay_writers:
            tags.artist = [person.name for person in screenplay_writers]
        return tags

    def movie_to_genres(self, o_movie):
        try:
            genre_ids = o_movie.genre_ids
        except AttributeError:
            return
        for genre_id in genre_ids:
            yield self.movie_genre_map[genre_id]

    def cite_movie(self, o_movie, cite_api=None):
        if cite_api is None:
            from qip.cite import default as cite_api
        return cite_api.cite_movie(
            **self.movie_to_tags(o_movie).as_str_dict())
