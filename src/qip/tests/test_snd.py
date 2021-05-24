#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

import unittest

from pathlib import Path
import operator
import os
import sys

import qip.mm
from qip.mm import MediaTagEnum, AlbumTags, FrameRate

import logging
#logging.basicConfig(level=logging.DEBUG)
log = logging.getLogger(__name__)

import reprlib
reprlib.aRepr.maxdict = 100

test_dir = Path(__file__).parent.absolute()


class test_snd(unittest.TestCase):

    @property
    def tmp_dir(self):
        return test_dir / f'tmp{Path(self.id()).suffix}'

    def test_AlbumTags(self):

        album_tags = AlbumTags()
        album_tags.title = '-title-'
        album_tags.year = 2019
        self.assertEqual(album_tags.title, '-title-')
        self.assertEqual(album_tags.year, 2019)
        self.assertEqual(operator.attrgetter('year', 'month', 'day')(album_tags.date), (2019, None, None))
        self.assertEqual(str(album_tags.date), '2019')
        self.assertIs(album_tags.artist, None)
        self.assertIn(MediaTagEnum.albumtitle, album_tags)
        self.assertIn(MediaTagEnum.title, album_tags)
        self.assertIn(MediaTagEnum.date, album_tags)
        self.assertIn(MediaTagEnum.year, album_tags)
        self.assertTrue(album_tags.contains('year'))
        self.assertTrue(album_tags.contains(MediaTagEnum.year))
        self.assertFalse(album_tags.contains(MediaTagEnum.year, strict=True))  # even with year->date
        self.assertIn(MediaTagEnum.composer, album_tags)
        self.assertTrue(album_tags.contains('composer'))
        self.assertTrue(album_tags.contains(MediaTagEnum.composer))
        self.assertFalse(album_tags.contains(MediaTagEnum.composer, strict=True))
        self.assertEqual(dict(album_tags),
                         {
                             #MediaTagEnum.albumtitle: '-title-',
                             MediaTagEnum.title: '-title-',
                             MediaTagEnum.date: qip.mm.MediaTagDate('2019'),
                         })

    def test_FrameRate_round_common(self):

        self.assertEqual(FrameRate(24000, 1000).round_common(),  FrameRate(24000, 1000))
        self.assertEqual(FrameRate(24000, 1001).round_common(),  FrameRate(24000, 1001))
        self.assertEqual(FrameRate(25000, 1000).round_common(),  FrameRate(25000, 1000))
        self.assertEqual(FrameRate(30000, 1000).round_common(),  FrameRate(30000, 1000))
        self.assertEqual(FrameRate(30000, 1001).round_common(),  FrameRate(30000, 1001))
        #self.assertEqual(FrameRate(1/0.033367).round_common(),  FrameRate(24000, 1001))

if __name__ == '__main__':
    unittest.main()
