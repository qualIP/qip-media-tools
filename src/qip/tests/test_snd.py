#!/usr/bin/env python3

import unittest
import operator

import qip.snd
from qip.snd import SoundTagEnum, AlbumTags

class test_snd(unittest.TestCase):

    def test_AlbumTags(self):

        album_tags = AlbumTags()
        album_tags.title = '-title-'
        album_tags.year = 2019
        self.assertEqual(album_tags.title, '-title-')
        self.assertEqual(album_tags.year, 2019)
        self.assertEqual(operator.attrgetter('year', 'month', 'day')(album_tags.date), (2019, None, None))
        self.assertEqual(str(album_tags.date), '2019')
        self.assertIs(album_tags.artist, None)
        self.assertIn(SoundTagEnum.albumtitle, album_tags)
        self.assertIn(SoundTagEnum.title, album_tags)
        self.assertIn(SoundTagEnum.date, album_tags)
        self.assertIn(SoundTagEnum.year, album_tags)
        self.assertTrue(album_tags.contains('year'))
        self.assertTrue(album_tags.contains(SoundTagEnum.year))
        self.assertFalse(album_tags.contains(SoundTagEnum.year, strict=True))  # even with year->date
        self.assertIn(SoundTagEnum.composer, album_tags)
        self.assertTrue(album_tags.contains('composer'))
        self.assertTrue(album_tags.contains(SoundTagEnum.composer))
        self.assertFalse(album_tags.contains(SoundTagEnum.composer, strict=True))
        self.assertEqual(dict(album_tags),
                         {
                             SoundTagEnum.albumtitle: '-title-',
                             SoundTagEnum.title: '-title-',
                             SoundTagEnum.date: qip.snd.SoundTagDate('2019'),
                         })

if __name__ == '__main__':
    unittest.main()

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
