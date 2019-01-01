
__all__ = (
    'MkvFile',
)

import logging
log = logging.getLogger(__name__)

import qip.snd as snd

class MkvFile(snd.SoundFile):

    @property
    def tag_writer(self):
        return snd.taged

# vim: ft=python ts=8 sw=4 sts=4 ai et fdm=marker
