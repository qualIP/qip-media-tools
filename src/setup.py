# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

"""A setuptools based setup module.

See:
https://packaging.python.org/en/latest/distributing.html
"""

# Always prefer setuptools over distutils
from setuptools import setup, find_packages, Extension
# To use a consistent encoding
from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

# Get the long description from the README file
with open(path.join(here, 'README.rst'), encoding='utf-8') as f:
    long_description = f.read()

setup(
    name='qip',

    # Versions should comply with PEP440.  For a discussion on single-sourcing
    # the version across setup.py and the project code, see
    # https://packaging.python.org/en/latest/single_source_version.html
    version='1.0.0.dev1',

    description='qualIP\'s Python project',
    long_description=long_description,

    # The project's main homepage.
    url='https://qualipsoft.com',

    # Author details
    author='Jean-Sébastien Trottier',
    author_email='jst@qualipsoft.com',

    # Choose your license
    license='Proprietary',

    # See https://pypi.python.org/pypi?%3Aaction=list_classifiers
    classifiers=[
        # How mature is this project? Common values are
        #   3 - Alpha
        #   4 - Beta
        #   5 - Production/Stable
        'Development Status :: 3 - Alpha',

        # Indicate who your project is intended for
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Application Frameworks',

        # Pick your license as you wish (should match "license" above)
        'License :: Other/Proprietary License',

        # Specify the Python versions you support here. In particular, ensure
        # that you indicate whether you support Python 2, Python 3 or both.
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
    ],

    # What does your project relate to?
    keywords='',

    # You can just specify the packages manually here if your project is
    # simple. Or you can use find_packages().
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),

    # Alternatively, if you want to distribute just a my_module.py, uncomment
    # this:
    #   py_modules=["my_module"],

    # List run-time dependencies here.  These will be installed by pip when
    # your project is installed. For an analysis of "install_requires" vs pip's
    # requirements files see:
    # https://packaging.python.org/en/latest/requirements.html
    install_requires=[
            'pexpect',
            'pint',
            'ConfigArgParse',
            'configobj',
            'mutagen>=1.42.0',
            'musicbrainzngs',
            'unidecode',
            'progress',
            'prompt_toolkit >= 3, <4',
            'tmdbv3api',
            'tvdb_api',
            'coloredlogs',
            'tabulate',
            'Send2Trash',
            'bs4',
            'lxml',
            'statsd',
            'pyxdg',
            ],

    # List additional groups of dependencies here (e.g. development
    # dependencies). You can install these using the following syntax,
    # for example:
    # $ pip install -e .[dev,test]
    extras_require={
        'dev': ['check-manifest'],
        'test': ['coverage'],
    },

    ext_modules = [
        Extension('qip._libdvdread_swig',
                  sources=['qip/libdvdread_swig_wrap.c',],
                  libraries=['dvdread',],
                  ),
        Extension('qip._libudfread_swig',
                  sources=['qip/libudfread_swig_wrap.c',],
                  libraries=['udfread',],
                  ),
    ],

    # If there are data files included in your packages that need to be
    # installed, specify them here.  If using Python 2.6 or less, then these
    # have to be included in MANIFEST.in as well.
    package_data={
        #'qip': ['package_data.dat'],
        'qip': [
            "bin/ffmpeg-2pass-pipe",
            "bin/fix-subtitles",
            "bin/stdout-wrapper",
        ],
    },

    # Although 'package_data' is the preferred approach, in some case you may
    # need to place data files outside of your packages. See:
    # http://docs.python.org/3.4/distutils/setupscript.html#installing-additional-files # noqa
    # In this case, 'data_file' will be installed into '<sys.prefix>/my_data'
    #data_files=[('my_data', ['data/data_file'])],
    data_files=[],

    # To provide executable scripts, use entry points in preference to the
    # "scripts" keyword. Entry points provide cross-platform support and allow
    # pip to create the appropriate form of executable for the target platform.
    entry_points={
        'console_scripts': [
            'bincuerip = qip.bin.bincuerip:main',
            'bincuetags = qip.bin.bincuetags:main',
            'cdrom-ready = qip.bin.cdrom_ready:main',
            'dl-playlist = qip.bin.dl_playlist:main',
            'librivox-dl = qip.bin.librivox_dl:main',
            'lsdvd = qip.bin.lsdvd:main',
            'mkbincue = qip.bin.mkbincue:main',
            'mkm4b = qip.bin.mkm4b:main',
            'mmdemux = qip.bin.mmdemux:main',
            'mmprobe = qip.bin.mmprobe:main',
            'mmrename = qip.bin.mmrename:main',
            'organize-media = qip.bin.organize_media:main',
            'taged = qip.bin.taged:main',
        ],
    },
)
