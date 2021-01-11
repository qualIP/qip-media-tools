# -*- coding: utf-8 -*-
# vim: set fileencoding=utf-8 :

__all__ = [
    ]

# SPDX-License-Identifier: GPL-2.0 WITH Linux-syscall-note 
#
# -- <linux/cdrom.h>
# General header file for linux CD-ROM drivers 
# Copyright (C) 1992         David Giller, rafetmad@oxy.edu
#               1994, 1995   Eberhard Mönkeberg, emoenke@gwdg.de
#               1996         David van Leeuwen, david@tm.tno.nl
#               1997, 1998   Erik Andersen, andersee@debian.org
#               1998-2002    Jens Axboe, axboe@suse.de

#ifndef _LINUX_CDROM_H
#define _LINUX_CDROM_H

#include <linux/types.h>
#include <asm/byteorder.h>

from pathlib import Path
import contextlib
import enum
import errno
import fcntl
import functools
import logging
import os
import time
log = logging.getLogger(__name__)

INT_MAX = 2147483647

########################################################
# As of Linux 2.1.x, all Linux CD-ROM application programs will use this 
# (and only this) include file.  It is my hope to provide Linux with
# a uniform interface between software accessing CD-ROMs and the various 
# device drivers that actually talk to the drives.  There may still be
# 23 different kinds of strange CD-ROM drives, but at least there will 
# now be one, and only one, Linux CD-ROM interface.
#
# Additionally, as of Linux 2.1.x, all Linux application programs 
# should use the O_NONBLOCK option when opening a CD-ROM device 
# for subsequent ioctl commands.  This allows for neat system errors 
# like "No medium found" or "Wrong medium type" upon attempting to 
# mount or play an empty slot, mount an audio disc, or play a data disc.
# Generally, changing an application program to support O_NONBLOCK
# is as easy as the following:
#       -    drive = open("/dev/cdrom", O_RDONLY);
#       +    drive = open("/dev/cdrom", O_RDONLY | O_NONBLOCK);
# It is worth the small change.
#
#  Patches for many common CD programs (provided by David A. van Leeuwen)
#  can be found at:  ftp://ftp.gwdg.de/pub/linux/cdrom/drivers/cm206/
# 
########################################################

# When a driver supports a certain function, but the cdrom drive we are 
# using doesn't, we will return the error EDRIVE_CANT_DO_THIS.  We will 
# borrow the "Operation not supported" error from the network folks to 
# accomplish this.  Maybe someday we will get a more targeted error code, 
# but this will do for now...
EDRIVE_CANT_DO_THIS = errno.EOPNOTSUPP

########################################################
# The CD-ROM IOCTL commands  -- these should be supported by 
# all the various cdrom drivers.  For the CD-ROM ioctls, we 
# will commandeer byte 0x53, or 'S'.
########################################################
CDROMPAUSE = 0x5301  # Pause Audio Operation  
CDROMRESUME = 0x5302  # Resume paused Audio Operation 
CDROMPLAYMSF = 0x5303  # Play Audio MSF (struct cdrom_msf) 
CDROMPLAYTRKIND = 0x5304  # Play Audio Track/index (struct cdrom_ti) 
CDROMREADTOCHDR = 0x5305  # Read TOC header (struct cdrom_tochdr) 
CDROMREADTOCENTRY = 0x5306  # Read TOC entry (struct cdrom_tocentry) 
CDROMSTOP = 0x5307  # Stop the cdrom drive 
CDROMSTART = 0x5308  # Start the cdrom drive 
CDROMEJECT = 0x5309  # Ejects the cdrom media 
CDROMVOLCTRL = 0x530a  # Control output volume (struct cdrom_volctrl) 
CDROMSUBCHNL = 0x530b  # Read subchannel data (struct cdrom_subchnl) 
CDROMREADMODE2 = 0x530c  # Read CDROM mode 2 data (2336 Bytes) (struct cdrom_read) 
CDROMREADMODE1 = 0x530d  # Read CDROM mode 1 data (2048 Bytes) (struct cdrom_read) 
CDROMREADAUDIO = 0x530e  # (struct cdrom_read_audio) 
CDROMEJECT_SW = 0x530f  # enable(1)/disable(0) auto-ejecting 
CDROMMULTISESSION = 0x5310  # Obtain the start-of-last-session address of multi session disks (struct cdrom_multisession) 
CDROM_GET_MCN = 0x5311  # Obtain the "Universal Product Code" if available (struct cdrom_mcn) 
CDROM_GET_UPC = CDROM_GET_MCN  # This one is deprecated, but here anyway for compatibility 
CDROMRESET = 0x5312  # hard-reset the drive 
CDROMVOLREAD = 0x5313  # Get the drive's volume setting (struct cdrom_volctrl) 
CDROMREADRAW = 0x5314  # read data in raw mode (2352 Bytes) (struct cdrom_read) 

# 
 # These ioctls are used only used in aztcd.c and optcd.c
 #
CDROMREADCOOKED = 0x5315  # read data in cooked mode 
CDROMSEEK = 0x5316  # seek msf address 

#
# This ioctl is only used by the scsi-cd driver.  
# It is for playing audio in logical block addressing mode.
#
CDROMPLAYBLK = 0x5317  # (struct cdrom_blk) 

# 
# These ioctls are only used in optcd.c
#
CDROMREADALL = 0x5318  # read all 2646 bytes 

# 
# These ioctls are (now) only in ide-cd.c for controlling 
# drive spindown time.  They should be implemented in the
# Uniform driver, via generic packet commands, GPCMD_MODE_SELECT_10,
# GPCMD_MODE_SENSE_10 and the GPMODE_POWER_PAGE...
#  -Erik
#
CDROMGETSPINDOWN = 0x531d
CDROMSETSPINDOWN = 0x531e

# 
# These ioctls are implemented through the uniform CD-ROM driver
# They _will_ be adopted by all CD-ROM drivers, when all the CD-ROM
# drivers are eventually ported to the uniform CD-ROM driver interface.
#
CDROMCLOSETRAY = 0x5319  # pendant of CDROMEJECT 
CDROM_SET_OPTIONS = 0x5320  # Set behavior options 
CDROM_CLEAR_OPTIONS = 0x5321  # Clear behavior options 
CDROM_SELECT_SPEED = 0x5322  # Set the CD-ROM speed 
CDROM_SELECT_DISC = 0x5323  # Select disc (for juke-boxes) 
CDROM_MEDIA_CHANGED = 0x5325  # Check is media changed  
CDROM_DRIVE_STATUS = 0x5326  # Get tray position, etc. 
CDROM_DISC_STATUS = 0x5327  # Get disc type, etc. 
CDROM_CHANGER_NSLOTS = 0x5328  # Get number of slots 
CDROM_LOCKDOOR = 0x5329  # lock or unlock door 
CDROM_DEBUG = 0x5330  # Turn debug messages on/off 
CDROM_GET_CAPABILITY = 0x5331  # get capabilities 

# Note that scsi/scsi_ioctl.h also uses 0x5382 - 0x5386.
# Future CDROM ioctls should be kept below 0x537F
#

# This ioctl is only used by sbpcd at the moment 
CDROMAUDIOBUFSIZ = 0x5382  # set the audio buffer size 
                    # conflict with SCSI_IOCTL_GET_IDLUN 

# DVD-ROM Specific ioctls 
DVD_READ_STRUCT = 0x5390  # Read structure 
DVD_WRITE_STRUCT = 0x5391  # Write structure 
DVD_AUTH = 0x5392  # Authentication 

CDROM_SEND_PACKET = 0x5393  # send a packet to the drive 
CDROM_NEXT_WRITABLE = 0x5394  # get next writable block 
CDROM_LAST_WRITTEN = 0x5395  # get last block written on disc 

########################################################
# CDROM IOCTL structures
########################################################

# # Address in MSF format 
# struct cdrom_msf0     
# {
#   __u8    minute;
#   __u8    second;
#   __u8    frame;
# };
# 
# # Address in either MSF or logical format 
# union cdrom_addr      
# {
#   struct cdrom_msf0   msf;
#   int         lba;
# };
# 
# # This struct is used by the CDROMPLAYMSF ioctl  
# struct cdrom_msf 
# {
#   __u8    cdmsf_min0; # start minute 
#   __u8    cdmsf_sec0; # start second 
#   __u8    cdmsf_frame0;   # start frame 
#   __u8    cdmsf_min1; # end minute 
#   __u8    cdmsf_sec1; # end second 
#   __u8    cdmsf_frame1;   # end frame 
# };
# 
# # This struct is used by the CDROMPLAYTRKIND ioctl 
# struct cdrom_ti 
# {
#   __u8    cdti_trk0;  # start track 
#   __u8    cdti_ind0;  # start index 
#   __u8    cdti_trk1;  # end track 
#   __u8    cdti_ind1;  # end index 
# };
# 
# # This struct is used by the CDROMREADTOCHDR ioctl 
# struct cdrom_tochdr   
# {
#   __u8    cdth_trk0;  # start track 
#   __u8    cdth_trk1;  # end track 
# };
# 
# # This struct is used by the CDROMVOLCTRL and CDROMVOLREAD ioctls 
# struct cdrom_volctrl
# {
#   __u8    channel0;
#   __u8    channel1;
#   __u8    channel2;
#   __u8    channel3;
# };
# 
# # This struct is used by the CDROMSUBCHNL ioctl 
# struct cdrom_subchnl 
# {
#   __u8    cdsc_format;
#   __u8    cdsc_audiostatus;
#   __u8    cdsc_adr:   4;
#   __u8    cdsc_ctrl:  4;
#   __u8    cdsc_trk;
#   __u8    cdsc_ind;
#   union cdrom_addr cdsc_absaddr;
#   union cdrom_addr cdsc_reladdr;
# };
# 
# 
# # This struct is used by the CDROMREADTOCENTRY ioctl 
# struct cdrom_tocentry 
# {
#   __u8    cdte_track;
#   __u8    cdte_adr    :4;
#   __u8    cdte_ctrl   :4;
#   __u8    cdte_format;
#   union cdrom_addr cdte_addr;
#   __u8    cdte_datamode;
# };
# 
# # This struct is used by the CDROMREADMODE1, and CDROMREADMODE2 ioctls 
# struct cdrom_read      
# {
#   int cdread_lba;
#   char    *cdread_bufaddr;
#   int cdread_buflen;
# };
# 
# # This struct is used by the CDROMREADAUDIO ioctl 
# struct cdrom_read_audio
# {
#   union cdrom_addr addr; # frame address 
#   __u8 addr_format;      # CDROM_LBA or CDROM_MSF 
#   int nframes;           # number of 2352-byte-frames to read at once 
#   __u8 *buf;      # frame buffer (size: nframes*2352 bytes) 
# };
# 
# # This struct is used with the CDROMMULTISESSION ioctl 
# struct cdrom_multisession
# {
#   union cdrom_addr addr; # frame address: start-of-last-session 
#                          #  (not the new "frame 16"!).  Only valid
#                          #  if the "xa_flag" is true.
#   __u8 xa_flag;        # 1: "is XA disk" 
#   __u8 addr_format;    # CDROM_LBA or CDROM_MSF 
# };
# 
# # This struct is used with the CDROM_GET_MCN ioctl.  
# # Very few audio discs actually have Universal Product Code information, 
# # which should just be the Medium Catalog Number on the box.  Also note 
# # that the way the codeis written on CD is _not_ uniform across all discs!
# #  
# struct cdrom_mcn 
# {
#   __u8 medium_catalog_number[14]; # 13 ASCII digits, null-terminated 
# };
# 
# # This is used by the CDROMPLAYBLK ioctl 
# struct cdrom_blk 
# {
#   unsigned from;
#   unsigned short len;
# };
# 
# CDROM_PACKET_SIZE = 12
# 
# CGC_DATA_UNKNOWN = 0
# CGC_DATA_WRITE = 1
# CGC_DATA_READ = 2
# CGC_DATA_NONE = 3
# 
# # for CDROM_PACKET_COMMAND ioctl 
# struct cdrom_generic_command
# {
#   unsigned char       cmd[CDROM_PACKET_SIZE];
#   unsigned char       *buffer;
#   unsigned int        buflen;
#   int         stat;
#   struct request_sense    *sense;
#   unsigned char       data_direction;
#   int         quiet;
#   int         timeout;
#   void            *reserved[1];   # unused, actually 
# };

#
# A CD-ROM physical sector size is 2048, 2052, 2056, 2324, 2332, 2336, 
# 2340, or 2352 bytes long.  
#
#         Sector types of the standard CD-ROM data formats:
#
# format   sector type               user data size (bytes)
# -----------------------------------------------------------------------------
#   1     (Red Book)    CD-DA          2352    (CD_FRAMESIZE_RAW)
#   2     (Yellow Book) Mode1 Form1    2048    (CD_FRAMESIZE)
#   3     (Yellow Book) Mode1 Form2    2336    (CD_FRAMESIZE_RAW0)
#   4     (Green Book)  Mode2 Form1    2048    (CD_FRAMESIZE)
#   5     (Green Book)  Mode2 Form2    2328    (2324+4 spare bytes)
#
#
#       The layout of the standard CD-ROM data formats:
# -----------------------------------------------------------------------------
# - audio (red):                  | audio_sample_bytes |
#                                 |        2352        |
#
# - data (yellow, mode1):         | sync - head - data - EDC - zero - ECC |
#                                 |  12  -   4  - 2048 -  4  -   8  - 276 |
#
# - data (yellow, mode2):         | sync - head - data |
#                                 |  12  -   4  - 2336 |
#
# - XA data (green, mode2 form1): | sync - head - sub - data - EDC - ECC |
#                                 |  12  -   4  -  8  - 2048 -  4  - 276 |
#
# - XA data (green, mode2 form2): | sync - head - sub - data - Spare |
#                                 |  12  -   4  -  8  - 2324 -  4    |
#
#

# Some generally useful CD-ROM information -- mostly based on the above 
CD_MINS = 74  # max. minutes per CD, not really a limit 
CD_SECS = 60  # seconds per minute 
CD_FRAMES = 75  # frames per second 
CD_SYNC_SIZE = 12  # 12 sync bytes per raw data frame 
CD_MSF_OFFSET = 150  # MSF numbering offset of first frame 
CD_CHUNK_SIZE = 24  # lowest-level "data bytes piece" 
CD_NUM_OF_CHUNKS = 98  # chunks per frame 
CD_FRAMESIZE_SUB = 96  # subchannel data "frame" size 
CD_HEAD_SIZE = 4  # header (address) bytes per raw data frame 
CD_SUBHEAD_SIZE = 8  # subheader bytes per raw XA data frame 
CD_EDC_SIZE = 4  # bytes EDC per most raw data frame types 
CD_ZERO_SIZE = 8  # bytes zero per yellow book mode 1 frame 
CD_ECC_SIZE = 276  # bytes ECC per most raw data frame types 
CD_FRAMESIZE = 2048  # bytes per frame, "cooked" mode 
CD_FRAMESIZE_RAW = 2352  # bytes per frame, "raw" mode 
CD_FRAMESIZE_RAWER = 2646  # The maximum possible returned bytes  
# most drives don't deliver everything: 
CD_FRAMESIZE_RAW1 = (CD_FRAMESIZE_RAW - CD_SYNC_SIZE)  # 2340
CD_FRAMESIZE_RAW0 = (CD_FRAMESIZE_RAW - CD_SYNC_SIZE - CD_HEAD_SIZE)  # 2336

CD_XA_HEAD = (CD_HEAD_SIZE + CD_SUBHEAD_SIZE)  # "before data" part of raw XA frame 
CD_XA_TAIL = (CD_EDC_SIZE + CD_ECC_SIZE)  # "after data" part of raw XA frame 
CD_XA_SYNC_HEAD = (CD_SYNC_SIZE + CD_XA_HEAD)  # sync bytes + header of XA frame 

# CD-ROM address types (cdrom_tocentry.cdte_format) 
CDROM_LBA = 0x01  # "logical block": first frame is #0 
CDROM_MSF = 0x02  # "minute-second-frame": binary, not bcd here! 

# bit to tell whether track is data or audio (cdrom_tocentry.cdte_ctrl) 
CDROM_DATA_TRACK = 0x04

# The leadout track is always 0xAA, regardless of # of tracks on disc 
CDROM_LEADOUT = 0xAA

# audio states (from SCSI-2, but seen with other drives, too) 
CDROM_AUDIO_INVALID = 0x00  # audio status not supported 
CDROM_AUDIO_PLAY = 0x11  # audio play operation in progress 
CDROM_AUDIO_PAUSED = 0x12  # audio play operation paused 
CDROM_AUDIO_COMPLETED = 0x13  # audio play successfully completed 
CDROM_AUDIO_ERROR = 0x14  # audio play stopped due to error 
CDROM_AUDIO_NO_STATUS = 0x15  # no current audio status to return 

# capability flags used with the uniform CD-ROM driver  
CDC_CLOSE_TRAY = 0x1  # caddy systems _can't_ close 
CDC_OPEN_TRAY = 0x2  # but _can_ eject.  
CDC_LOCK = 0x4  # disable manual eject 
CDC_SELECT_SPEED = 0x8  # programmable speed 
CDC_SELECT_DISC = 0x10  # select disc from juke-box 
CDC_MULTI_SESSION = 0x20  # read sessions>1 
CDC_MCN = 0x40  # Medium Catalog Number 
CDC_MEDIA_CHANGED = 0x80  # media changed 
CDC_PLAY_AUDIO = 0x100  # audio functions 
CDC_RESET = 0x200  # hard reset device 
CDC_DRIVE_STATUS = 0x800  # driver implements drive status 
CDC_GENERIC_PACKET = 0x1000  # driver implements generic packets 
CDC_CD_R = 0x2000  # drive is a CD-R 
CDC_CD_RW = 0x4000  # drive is a CD-RW 
CDC_DVD = 0x8000  # drive is a DVD 
CDC_DVD_R = 0x10000  # drive can write DVD-R 
CDC_DVD_RAM = 0x20000  # drive can write DVD-RAM 
CDC_MO_DRIVE = 0x40000  # drive is an MO device 
CDC_MRW = 0x80000  # drive can read MRW 
CDC_MRW_W = 0x100000  # drive can write MRW 
CDC_RAM = 0x200000  # ok to open for WRITE 

# drive status possibilities returned by CDROM_DRIVE_STATUS ioctl 
class CdromDriveStatus(enum.IntEnum):
    CDS_NO_INFO = 0  # if not implemented 
    CDS_NO_DISC = 1
    CDS_TRAY_OPEN = 2
    CDS_DRIVE_NOT_READY = 3
    CDS_DISC_OK = 4

class CdromDiscStatus(enum.IntEnum):
    # return values for the CDROM_DISC_STATUS ioctl 
    # can also return CDS_NO_[INFO|DISC], from above 
    CDS_AUDIO = 100
    CDS_DATA_1 = 101
    CDS_DATA_2 = 102
    CDS_XA_2_1 = 103
    CDS_XA_2_2 = 104
    CDS_MIXED = 105

# User-configurable behavior options for the uniform CD-ROM driver 
CDO_AUTO_CLOSE = 0x1  # close tray on first open() 
CDO_AUTO_EJECT = 0x2  # open tray on last release() 
CDO_USE_FFLAGS = 0x4  # use O_NONBLOCK information on open 
CDO_LOCK = 0x8  # lock tray on open files 
CDO_CHECK_TYPE = 0x10  # check type on open for data 

# Special codes used when specifying changer slots. 
CDSL_NONE = (INT_MAX - 1)
CDSL_CURRENT = INT_MAX

# For partition based multisession access. IDE can handle 64 partitions
# per drive - SCSI CD-ROM's use minors to differentiate between the
# various drives, so we can't do multisessions the same way there.
# Use the -o session=x option to mount on them.
#
CD_PART_MAX = 64
CD_PART_MASK = (CD_PART_MAX - 1)

######################################################################
# Generic Packet commands, MMC commands, and such
######################################################################

# The generic packet command opcodes for CD/DVD Logical Units,
# From Table 57 of the SFF8090 Ver. 3 (Mt. Fuji) draft standard.
GPCMD_BLANK = 0xa1
GPCMD_CLOSE_TRACK = 0x5b
GPCMD_FLUSH_CACHE = 0x35
GPCMD_FORMAT_UNIT = 0x04
GPCMD_GET_CONFIGURATION = 0x46
GPCMD_GET_EVENT_STATUS_NOTIFICATION = 0x4a
GPCMD_GET_PERFORMANCE = 0xac
GPCMD_INQUIRY = 0x12
GPCMD_LOAD_UNLOAD = 0xa6
GPCMD_MECHANISM_STATUS = 0xbd
GPCMD_MODE_SELECT_10 = 0x55
GPCMD_MODE_SENSE_10 = 0x5a
GPCMD_PAUSE_RESUME = 0x4b
GPCMD_PLAY_AUDIO_10 = 0x45
GPCMD_PLAY_AUDIO_MSF = 0x47
GPCMD_PLAY_AUDIO_TI = 0x48
GPCMD_PLAY_CD = 0xbc
GPCMD_PREVENT_ALLOW_MEDIUM_REMOVAL = 0x1e
GPCMD_READ_10 = 0x28
GPCMD_READ_12 = 0xa8
GPCMD_READ_BUFFER = 0x3c
GPCMD_READ_BUFFER_CAPACITY = 0x5c
GPCMD_READ_CDVD_CAPACITY = 0x25
GPCMD_READ_CD = 0xbe
GPCMD_READ_CD_MSF = 0xb9
GPCMD_READ_DISC_INFO = 0x51
GPCMD_READ_DVD_STRUCTURE = 0xad
GPCMD_READ_FORMAT_CAPACITIES = 0x23
GPCMD_READ_HEADER = 0x44
GPCMD_READ_TRACK_RZONE_INFO = 0x52
GPCMD_READ_SUBCHANNEL = 0x42
GPCMD_READ_TOC_PMA_ATIP = 0x43
GPCMD_REPAIR_RZONE_TRACK = 0x58
GPCMD_REPORT_KEY = 0xa4
GPCMD_REQUEST_SENSE = 0x03
GPCMD_RESERVE_RZONE_TRACK = 0x53
GPCMD_SEND_CUE_SHEET = 0x5d
GPCMD_SCAN = 0xba
GPCMD_SEEK = 0x2b
GPCMD_SEND_DVD_STRUCTURE = 0xbf
GPCMD_SEND_EVENT = 0xa2
GPCMD_SEND_KEY = 0xa3
GPCMD_SEND_OPC = 0x54
GPCMD_SET_READ_AHEAD = 0xa7
GPCMD_SET_STREAMING = 0xb6
GPCMD_START_STOP_UNIT = 0x1b
GPCMD_STOP_PLAY_SCAN = 0x4e
GPCMD_TEST_UNIT_READY = 0x00
GPCMD_VERIFY_10 = 0x2f
GPCMD_WRITE_10 = 0x2a
GPCMD_WRITE_12 = 0xaa
GPCMD_WRITE_AND_VERIFY_10 = 0x2e
GPCMD_WRITE_BUFFER = 0x3b
# This is listed as optional in ATAPI 2.6, but is (curiously) 
# missing from Mt. Fuji, Table 57.  It _is_ mentioned in Mt. Fuji
# Table 377 as an MMC command for SCSi devices though...  Most ATAPI
# drives support it.
GPCMD_SET_SPEED = 0xbb
# This seems to be a SCSI specific CD-ROM opcode 
# to play data at track/index
GPCMD_PLAYAUDIO_TI = 0x48
#
# From MS Media Status Notification Support Specification. For
# older drives only.
#
GPCMD_GET_MEDIA_STATUS = 0xda

# Mode page codes for mode sense/set 
GPMODE_VENDOR_PAGE = 0x00
GPMODE_R_W_ERROR_PAGE = 0x01
GPMODE_WRITE_PARMS_PAGE = 0x05
GPMODE_WCACHING_PAGE = 0x08
GPMODE_AUDIO_CTL_PAGE = 0x0e
GPMODE_POWER_PAGE = 0x1a
GPMODE_FAULT_FAIL_PAGE = 0x1c
GPMODE_TO_PROTECT_PAGE = 0x1d
GPMODE_CAPABILITIES_PAGE = 0x2a
GPMODE_ALL_PAGES = 0x3f
# Not in Mt. Fuji, but in ATAPI 2.6 -- deprecated now in favor
# of MODE_SENSE_POWER_PAGE
GPMODE_CDROM_PAGE = 0x0d



# DVD struct types 
# DVD_STRUCT_PHYSICAL = 0x00
# DVD_STRUCT_COPYRIGHT = 0x01
# DVD_STRUCT_DISCKEY = 0x02
# DVD_STRUCT_BCA = 0x03
# DVD_STRUCT_MANUFACT = 0x04
# 
# struct dvd_layer {
#   __u8 book_version   : 4;
#   __u8 book_type      : 4;
#   __u8 min_rate       : 4;
#   __u8 disc_size      : 4;
#   __u8 layer_type     : 4;
#   __u8 track_path     : 1;
#   __u8 nlayers        : 2;
#   __u8 track_density  : 4;
#   __u8 linear_density : 4;
#   __u8 bca        : 1;
#   __u32 start_sector;
#   __u32 end_sector;
#   __u32 end_sector_l0;
# };
# 
# DVD_LAYERS = 4
# 
# struct dvd_physical {
#   __u8 type;
#   __u8 layer_num;
#   struct dvd_layer layer[DVD_LAYERS];
# };
# 
# struct dvd_copyright {
#   __u8 type;
# 
#   __u8 layer_num;
#   __u8 cpst;
#   __u8 rmi;
# };
# 
# struct dvd_disckey {
#   __u8 type;
# 
#   unsigned agid       : 2;
#   __u8 value[2048];
# };
# 
# struct dvd_bca {
#   __u8 type;
# 
#   int len;
#   __u8 value[188];
# };
# 
# struct dvd_manufact {
#   __u8 type;
# 
#   __u8 layer_num;
#   int len;
#   __u8 value[2048];
# };
# 
# typedef union {
#   __u8 type;
# 
#   struct dvd_physical physical;
#   struct dvd_copyright    copyright;
#   struct dvd_disckey  disckey;
#   struct dvd_bca      bca;
#   struct dvd_manufact manufact;
# } dvd_struct;

#
# DVD authentication ioctl
#

# Authentication states 
DVD_LU_SEND_AGID = 0
DVD_HOST_SEND_CHALLENGE = 1
DVD_LU_SEND_KEY1 = 2
DVD_LU_SEND_CHALLENGE = 3
DVD_HOST_SEND_KEY2 = 4

# Termination states 
DVD_AUTH_ESTABLISHED = 5
DVD_AUTH_FAILURE = 6

# Other functions 
DVD_LU_SEND_TITLE_KEY = 7
DVD_LU_SEND_ASF = 8
DVD_INVALIDATE_AGID = 9
DVD_LU_SEND_RPC_STATE = 10
DVD_HOST_SEND_RPC_STATE = 11

# # State data 
# typedef __u8 dvd_key[5];      # 40-bit value, MSB is first elem. 
# typedef __u8 dvd_challenge[10];   # 80-bit value, MSB is first elem. 
# 
# struct dvd_lu_send_agid {
#   __u8 type;
#   unsigned agid       : 2;
# };
# 
# struct dvd_host_send_challenge {
#   __u8 type;
#   unsigned agid       : 2;
# 
#   dvd_challenge chal;
# };
# 
# struct dvd_send_key {
#   __u8 type;
#   unsigned agid       : 2;
# 
#   dvd_key key;
# };
# 
# struct dvd_lu_send_challenge {
#   __u8 type;
#   unsigned agid       : 2;
# 
#   dvd_challenge chal;
# };

DVD_CPM_NO_COPYRIGHT = 0
DVD_CPM_COPYRIGHTED = 1

DVD_CP_SEC_NONE = 0
DVD_CP_SEC_EXIST = 1

DVD_CGMS_UNRESTRICTED = 0
DVD_CGMS_SINGLE = 2
DVD_CGMS_RESTRICTED = 3

# struct dvd_lu_send_title_key {
#   __u8 type;
#   unsigned agid       : 2;
# 
#   dvd_key title_key;
#   int lba;
#   unsigned cpm        : 1;
#   unsigned cp_sec     : 1;
#   unsigned cgms       : 2;
# };
# 
# struct dvd_lu_send_asf {
#   __u8 type;
#   unsigned agid       : 2;
# 
#   unsigned asf        : 1;
# };
# 
# struct dvd_host_send_rpcstate {
#   __u8 type;
#   __u8 pdrc;
# };
# 
# struct dvd_lu_send_rpcstate {
#   __u8 type       : 2;
#   __u8 vra        : 3;
#   __u8 ucca       : 3;
#   __u8 region_mask;
#   __u8 rpc_scheme;
# };
# 
# typedef union {
#   __u8 type;
# 
#   struct dvd_lu_send_agid     lsa;
#   struct dvd_host_send_challenge  hsc;
#   struct dvd_send_key     lsk;
#   struct dvd_lu_send_challenge    lsc;
#   struct dvd_send_key     hsk;
#   struct dvd_lu_send_title_key    lstk;
#   struct dvd_lu_send_asf      lsasf;
#   struct dvd_host_send_rpcstate   hrpcs;
#   struct dvd_lu_send_rpcstate lrpcs;
# } dvd_authinfo;
# 
# struct request_sense {
# #if defined(__BIG_ENDIAN_BITFIELD)
#   __u8 valid      : 1;
#   __u8 error_code     : 7;
# #elif defined(__LITTLE_ENDIAN_BITFIELD)
#   __u8 error_code     : 7;
#   __u8 valid      : 1;
# #endif
#   __u8 segment_number;
# #if defined(__BIG_ENDIAN_BITFIELD)
#   __u8 reserved1      : 2;
#   __u8 ili        : 1;
#   __u8 reserved2      : 1;
#   __u8 sense_key      : 4;
# #elif defined(__LITTLE_ENDIAN_BITFIELD)
#   __u8 sense_key      : 4;
#   __u8 reserved2      : 1;
#   __u8 ili        : 1;
#   __u8 reserved1      : 2;
# #endif
#   __u8 information[4];
#   __u8 add_sense_len;
#   __u8 command_info[4];
#   __u8 asc;
#   __u8 ascq;
#   __u8 fruc;
#   __u8 sks[3];
#   __u8 asb[46];
# };

#
# feature profile
#
CDF_RWRT = 0x0020  # "Random Writable" 
CDF_HWDM = 0x0024  # "Hardware Defect Management" 
CDF_MRW = 0x0028

#
# media status bits
#
CDM_MRW_NOTMRW = 0
CDM_MRW_BGFORMAT_INACTIVE = 1
CDM_MRW_BGFORMAT_ACTIVE = 2
CDM_MRW_BGFORMAT_COMPLETE = 3

#
# mrw address spaces
#
MRW_LBA_DMA = 0
MRW_LBA_GAA = 1

#
# mrw mode pages (first is deprecated) -- probed at init time and
# cdi->mrw_mode_page is set
#
MRW_MODE_PC_PRE1 = 0x2c
MRW_MODE_PC = 0x03

# struct mrw_feature_desc {
#   __be16 feature_code;
# #if defined(__BIG_ENDIAN_BITFIELD)
#   __u8 reserved1      : 2;
#   __u8 feature_version    : 4;
#   __u8 persistent     : 1;
#   __u8 curr       : 1;
# #elif defined(__LITTLE_ENDIAN_BITFIELD)
#   __u8 curr       : 1;
#   __u8 persistent     : 1;
#   __u8 feature_version    : 4;
#   __u8 reserved1      : 2;
# #endif
#   __u8 add_len;
# #if defined(__BIG_ENDIAN_BITFIELD)
#   __u8 reserved2      : 7;
#   __u8 write      : 1;
# #elif defined(__LITTLE_ENDIAN_BITFIELD)
#   __u8 write      : 1;
#   __u8 reserved2      : 7;
# #endif
#   __u8 reserved3;
#   __u8 reserved4;
#   __u8 reserved5;
# };
# 
# # cf. mmc4r02g.pdf 5.3.10 Random Writable Feature (0020h) pg 197 of 635 
# struct rwrt_feature_desc {
#   __be16 feature_code;
# #if defined(__BIG_ENDIAN_BITFIELD)
#   __u8 reserved1      : 2;
#   __u8 feature_version    : 4;
#   __u8 persistent     : 1;
#   __u8 curr       : 1;
# #elif defined(__LITTLE_ENDIAN_BITFIELD)
#   __u8 curr       : 1;
#   __u8 persistent     : 1;
#   __u8 feature_version    : 4;
#   __u8 reserved1      : 2;
# #endif
#   __u8 add_len;
#   __u32 last_lba;
#   __u32 block_size;
#   __u16 blocking;
# #if defined(__BIG_ENDIAN_BITFIELD)
#   __u8 reserved2      : 7;
#   __u8 page_present   : 1;
# #elif defined(__LITTLE_ENDIAN_BITFIELD)
#   __u8 page_present   : 1;
#   __u8 reserved2      : 7;
# #endif
#   __u8 reserved3;
# };
# 
# typedef struct {
#   __be16 disc_information_length;
# #if defined(__BIG_ENDIAN_BITFIELD)
#   __u8 reserved1          : 3;
#         __u8 erasable         : 1;
#         __u8 border_status        : 2;
#         __u8 disc_status      : 2;
# #elif defined(__LITTLE_ENDIAN_BITFIELD)
#         __u8 disc_status      : 2;
#         __u8 border_status        : 2;
#         __u8 erasable         : 1;
#   __u8 reserved1          : 3;
# #else
# #error "Please fix <asm/byteorder.h>"
# #endif
#   __u8 n_first_track;
#   __u8 n_sessions_lsb;
#   __u8 first_track_lsb;
#   __u8 last_track_lsb;
# #if defined(__BIG_ENDIAN_BITFIELD)
#   __u8 did_v          : 1;
#         __u8 dbc_v            : 1;
#         __u8 uru          : 1;
#         __u8 reserved2            : 2;
#   __u8 dbit           : 1;
#   __u8 mrw_status         : 2;
# #elif defined(__LITTLE_ENDIAN_BITFIELD)
#   __u8 mrw_status         : 2;
#   __u8 dbit           : 1;
#         __u8 reserved2            : 2;
#         __u8 uru          : 1;
#         __u8 dbc_v            : 1;
#   __u8 did_v          : 1;
# #endif
#   __u8 disc_type;
#   __u8 n_sessions_msb;
#   __u8 first_track_msb;
#   __u8 last_track_msb;
#   __u32 disc_id;
#   __u32 lead_in;
#   __u32 lead_out;
#   __u8 disc_bar_code[8];
#   __u8 reserved3;
#   __u8 n_opc;
# } disc_information;
# 
# typedef struct {
#   __be16 track_information_length;
#   __u8 track_lsb;
#   __u8 session_lsb;
#   __u8 reserved1;
# #if defined(__BIG_ENDIAN_BITFIELD)
#   __u8 reserved2          : 2;
#         __u8 damage           : 1;
#         __u8 copy         : 1;
#         __u8 track_mode           : 4;
#   __u8 rt             : 1;
#   __u8 blank          : 1;
#   __u8 packet         : 1;
#   __u8 fp             : 1;
#   __u8 data_mode          : 4;
#   __u8 reserved3          : 6;
#   __u8 lra_v          : 1;
#   __u8 nwa_v          : 1;
# #elif defined(__LITTLE_ENDIAN_BITFIELD)
#         __u8 track_mode           : 4;
#         __u8 copy         : 1;
#         __u8 damage           : 1;
#   __u8 reserved2          : 2;
#   __u8 data_mode          : 4;
#   __u8 fp             : 1;
#   __u8 packet         : 1;
#   __u8 blank          : 1;
#   __u8 rt             : 1;
#   __u8 nwa_v          : 1;
#   __u8 lra_v          : 1;
#   __u8 reserved3          : 6;
# #endif
#   __be32 track_start;
#   __be32 next_writable;
#   __be32 free_blocks;
#   __be32 fixed_packet_size;
#   __be32 track_size;
#   __be32 last_rec_address;
# } track_information;
# 
# struct feature_header {
#   __u32 data_len;
#   __u8 reserved1;
#   __u8 reserved2;
#   __u16 curr_profile;
# };
# 
# struct mode_page_header {
#   __be16 mode_data_length;
#   __u8 medium_type;
#   __u8 reserved1;
#   __u8 reserved2;
#   __u8 reserved3;
#   __be16 desc_length;
# };
# 
# # removable medium feature descriptor 
# struct rm_feature_desc {
#   __be16 feature_code;
# #if defined(__BIG_ENDIAN_BITFIELD)
#   __u8 reserved1:2;
#   __u8 feature_version:4;
#   __u8 persistent:1;
#   __u8 curr:1;
# #elif defined(__LITTLE_ENDIAN_BITFIELD)
#   __u8 curr:1;
#   __u8 persistent:1;
#   __u8 feature_version:4;
#   __u8 reserved1:2;
# #endif
#   __u8 add_len;
# #if defined(__BIG_ENDIAN_BITFIELD)
#   __u8 mech_type:3;
#   __u8 load:1;
#   __u8 eject:1;
#   __u8 pvnt_jmpr:1;
#   __u8 dbml:1;
#   __u8 lock:1;
# #elif defined(__LITTLE_ENDIAN_BITFIELD)
#   __u8 lock:1;
#   __u8 dbml:1;
#   __u8 pvnt_jmpr:1;
#   __u8 eject:1;
#   __u8 load:1;
#   __u8 mech_type:3;
# #endif
#   __u8 reserved2;
#   __u8 reserved3;
#   __u8 reserved4;
# };

#endif # _LINUX_CDROM_H 

def _resolve_cdrom_device(device=None):
    if device is None:
        device = os.environ.get('CDROM', '/dev/cdrom')
    device = Path(device).resolve()
    return device

def _open_cdrom_device(*, device=None, **kwargs):
    device = _resolve_cdrom_device(device=device)
    return open(device, **kwargs)

def _cdrom_device_ioctl(*, fd=None, device=None, request, return_type=None):
    if fd is not None:
        # if type(fd) is not int:
        #     fd = fd.fileno()
        return fcntl.ioctl(fd, request)
    with _open_cdrom_device(device=device) as fp:
        return return_type(_cdrom_device_ioctl(fd=fp, request=request, return_type=return_type))

cdrom_drive_status = functools.partial(_cdrom_device_ioctl,
                                       request=CDROM_DRIVE_STATUS,
                                       return_type=CdromDriveStatus)

cdrom_disk_status = functools.partial(_cdrom_device_ioctl,
                                       request=CDROM_DISC_STATUS,
                                       return_type=CdromDiscStatus)

def cdrom_ready(device=None, timeout=0, progress_bar=None):
    assert timeout >= 0
    t0 = time.perf_counter() if timeout else None
    device = _resolve_cdrom_device(device=device)

    with contextlib.ExitStack() as exit_stack:

        if progress_bar is True:
            progress_bar = None
            try:
                from qip.utils import ProgressBar
            except ImportError:
                pass
            else:
                progress_bar = ProgressBar('CDROM ready?')
                exit_stack.callback(progress_bar.finish)
        if progress_bar:
            progress_bar.timeout = timeout
            progress_bar.state = ''
            progress_bar.suffix = '[%(elapsed).1f/%(timeout).1f] %(state)s'
            progress_bar.update()

        while True:
            try:
                fp = _open_cdrom_device(device=device)
            except OSError as e:
                log.debug(e)
                if progress_bar:
                    progress_bar.state = e
                    progress_bar.update()
                if e.errno == errno.ENOMEDIUM:
                    if timeout and time.perf_counter() <= t0 + timeout:
                        time.sleep(0.1)
                        continue
                if progress_bar:
                    if timeout:
                        # progress_bar.state += ' -> timeout!'
                        progress_bar.update()
                return False
            break
        with fp:
            old_status = None
            while True:
                status = cdrom_drive_status(fd=fp)
                if status != old_status:
                    status = CdromDriveStatus(status)
                    log.debug('CDROM status=%r', status)
                    old_status = status
                    if progress_bar:
                        progress_bar.state = status.name
                        progress_bar.update()
                if status is CdromDriveStatus.CDS_DISC_OK:
                    break
                if timeout and time.perf_counter() <= t0 + timeout:
                    time.sleep(0.1)
                    continue
                if progress_bar:
                    if timeout:
                        # progress_bar.state += ' -> timeout!'
                        progress_bar.update()
                return False
            while True:
                try:
                    fp.read(2048)
                except Exception as e:
                    log.debug('Exception: %r', e)
                    if progress_bar:
                        progress_bar.state = e
                        progress_bar.update()
                    if timeout and time.perf_counter() <= t0 + timeout:
                        time.sleep(0.1)
                        continue
                    return False
                break
            if progress_bar:
                progress_bar.state = 'Ready!'
                progress_bar.update()

    return True

def read_dvd_title(dvd_file):
    with open(dvd_file, 'rb') as fp:
        fp.seek(32808)
        s = fp.read(32)
    s = s.decode()
    s = s.strip()
    return s
