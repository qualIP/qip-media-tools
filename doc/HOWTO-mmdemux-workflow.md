[![Hits](https://hits.seeyoufarm.com/api/count/incr/badge.svg?url=https%3A%2F%2Fgithub.com%2FqualIP%2Fqip-media-tools%2Fedit%2Fmain%2Fdoc%2FHOWTO-mmdemux-workflow.md&count_bg=%2379C83D&title_bg=%23555555&icon=&icon_color=%23E7E7E7&title=hits&edge_flat=false)](https://hits.seeyoufarm.com)

mmdemux proposed workflow
=========================

[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/biz/fund?id=4CZC3J57FXJVE)

➠ Go back to [qualIP's Media Tools](https://github.com/qualIP/qip-media-tools#qualips-media-tools).

Here's a proposed movie conversion workflow.

1. First, run in "interactive batch mode" to have mmdemux ask some initial
   setup questions.
2. Then, let it run until all automated conversion and optimization operations
   are complete (This can easily take several hours).
3. Finally, run again in "full interactive" (non-batch) to manually help in any
   remaining work.
4. Organize the resulting movie in your media library.

Table of Contents:
<!--ts-->
* [mmdemux proposed workflow](#mmdemux-proposed-workflow)
   * [Conversion setup using interactive mode](#conversion-setup-using-interactive-mode)
   * [Automated conversion using batch mode](#automated-conversion-using-batch-mode)
   * [Final manual steps using interactive mode](#final-manual-steps-using-interactive-mode)
   * [Organize in your media library](#organize-in-your-media-library)
* [Tips](#tips)
   * [Setting default options](#setting-default-options)
<!--te-->

Conversion setup using interactive mode
---------------------------------------

The following command starts the conversion process:

    $ mmdemux --mux TheAmerican/title_t00.mkv --chain --ocr-subtitles=forced --external-subtitles=non-forced --interactive --batch
    2021-01-01 00:00:00 INFO Muxing TheAmerican/title_t00.mkv...

The `--chain` arguments instructs to perform all actions in a chain in order to
produce an optimize movie (--mux, --optimize, --demux, --verify).

The `--ocr-subtitles=forced --external-subtitles=non-forced` arguments specify
desired conversions. In this case all subtitles should be output as external
files except forced subtitles which should be converted to WebVTT text files
to be included in the movie.

By default, cropping (`--crop`) is enabled.

mmdemux begins by asking some initial tagging questions. Here the `search`
command is used to bring up a dialog to search the online "The Movie DB" for
the movie title and allows selecting the correct match:

    Initial tags setup

    mmdemux(init)> help
    Initial tags setup

    positional arguments:
      {help,h,?,edit,search,continue,c,quit,q}
			    Commands
	help (h, ?)         Print this help
	edit                Edit tags
	search              Search The Movie DB
	continue (c)        Continue the muxing action -- done
	quit (q)            Quit

    mmdemux(init)> search

	       ┌─────| TheAmerican/title_t00.mkv |──────┐
	       │                                        │
	       │ Please input search query:             │
	       │                                        │
	       │ The American                           │
	       │                                        │
	       │        <    OK    > <  Cancel  >       │
	       │                                        │
	       └────────────────────────────────────────┘

    ┌──────────────────| Please select a movie |───────────────────┐
    │                                                              │
    │                                                              │
    │                                                              │
    │ (*) The American. 2010. (#27579) -- Dispatched to a small I^ │
    │ ( ) The American President. 1995. (#9087) -- Widowed U.S. p  │
    │ ( ) The American Meme. 2018. (#520370) -- Paris Hilton, the  │
    │ ( ) The American Side. 2016. (#343010) -- Following a myste  │
    │ ( ) The American Sector. 2020. (#665732) -- A documentary a  │
    │ ( ) The American Mall. 2008. (#25041) -- The executive prod  │
    │ ( ) Requiem for the American Dream. 2015. (#333377) -- Thro  │
    │ ( ) The Myth of the American Sleepover. 2011. (#70588) -- F  │
    │ ( ) The American Scream. 2012. (#134255) -- An original doc  │
    │ ( ) The American Astronaut. 2001. (#21538) -- Samual Curtisv │
    │                                                              │
    │                   <    Ok    > <  Cancel  >                  │
    │                                                              │
    └──────────────────────────────────────────────────────────────┘

    2021-01-01 00:00:00 INFO TheAmerican/title_t00.mkv: The American. 2010. DVD.
    Initial tags setup
    The American. 2010. DVD.

From this information, mmdemux gathers the precise title and release date of
the movie which will come useful when tagging the final optimized movie. You
can later modify this tag information by editing the "tags" section in the
mux.json file.

Automated conversion using batch mode
-------------------------------------

Now that initial questions are done, let's tell mmdemux to continue with the
conversion in a fully automated way:

    mmdemux(init)> continue

Muxing action is performed which splits the movie into its various video,
audio, subtitle and chapter parts:

    2021-01-01 00:00:00 INFO Will extract video stream #0 w/ mkvextract: track-00-video.mp2v
    2021-01-01 00:00:00 INFO Will extract audio stream #1 w/ mkvextract: track-01-audio.eng.ac3
    2021-01-01 00:00:00 INFO Will extract audio stream #2 w/ mkvextract: track-02-audio.eng.ac3
    2021-01-01 00:00:00 INFO Will extract audio stream #3 w/ mkvextract: track-03-audio.eng.ac3
    2021-01-01 00:00:00 INFO Will extract audio stream #4 w/ mkvextract: track-04-audio.fra.ac3
    2021-01-01 00:00:00 INFO Will extract subtitle stream #5 w/ mkvextract: track-05-subtitle.eng.sub
    2021-01-01 00:00:00 INFO Will extract subtitle stream #6 w/ mkvextract: track-06-subtitle.fra.sub
    2021-01-01 00:00:00 INFO Will extract subtitle stream #7 w/ mkvextract: track-07-subtitle.fra.sub
    2021-01-01 00:00:00 INFO Extract tracks w/ mkvextract...
    Extracting track 0 with the CodecID 'V_MPEG2' to the file 'TheAmerican/title_t00/track-00-video.mp2v'. Container format: MPEG-1/-2 program stream
    Extracting track 1 with the CodecID 'A_AC3' to the file 'TheAmerican/title_t00/track-01-audio.eng.ac3'. Container format: Dolby Digital (AC-3)
    Extracting track 2 with the CodecID 'A_AC3' to the file 'TheAmerican/title_t00/track-02-audio.eng.ac3'. Container format: Dolby Digital (AC-3)
    Extracting track 3 with the CodecID 'A_AC3' to the file 'TheAmerican/title_t00/track-03-audio.eng.ac3'. Container format: Dolby Digital (AC-3)
    Extracting track 4 with the CodecID 'A_AC3' to the file 'TheAmerican/title_t00/track-04-audio.fra.ac3'. Container format: Dolby Digital (AC-3)
    Extracting track 5 with the CodecID 'S_VOBSUB' to the file 'TheAmerican/title_t00/track-05-subtitle.eng.sub'. Container format: VobSubs
    Extracting track 6 with the CodecID 'S_VOBSUB' to the file 'TheAmerican/title_t00/track-06-subtitle.fra.sub'. Container format: VobSubs
    Extracting track 7 with the CodecID 'S_VOBSUB' to the file 'TheAmerican/title_t00/track-07-subtitle.fra.sub'. Container format: VobSubs
    Progress: 100%
    2021-01-01 00:00:00 INFO Detected subtitle stream #7 (fra) is forced

A summary of the movie is then printed. Here you can see the various streams as they were detected:

      Index     Codec                              Original        Size    Extension    Language    Title  Disposition
    -------  --------  ------------------------------------  ----------  -----------  ----------  -------  -------------
	  0  video     mpeg2video, Main, 720x480, 279:157    5724205568  .mp2v        und
	  1  audio     ac3, 5.1(side), 448kbps, 48kHz, fltp   352497152  .ac3         eng                  default
	  2  audio     ac3, stereo, 192kbps, 48kHz, fltp      151070208  .ac3         eng
	  3  audio     ac3, stereo, 192kbps, 48kHz, fltp      151070208  .ac3         eng
	  4  audio     ac3, 5.1(side), 384kbps, 48kHz, fltp   302140416  .ac3         fra
	  5  subtitle  dvd_subtitle                             1808384  .sub         eng                  default, *568
	  6  subtitle  dvd_subtitle                             1632256  .sub         fra                  *505
	  7  subtitle  dvd_subtitle                              126976  .sub         fra                  forced, *40

At this point you can stop mmdemux and modify the generated mux.json file to
tweak it any way you like.

But this time, let's just watch what mmdemux does on its own. First, the
`--optimize` action:

    2021-01-01 00:00:00 INFO Optimizing TheAmerican/title_t00...
    2021-01-01 00:00:00 INFO Analyze field order...
    iterate frames |################################| 60/60 (0:00:00 remaining)
    2021-01-01 00:00:00 WARNING Detected field order 23pulldown at 24000/1001 (23.976) fps based on temporal pattern near end of analysis section 'T2T3B2B3T2T3B2B3'
    2021-01-01 00:00:00 INFO Pullup w/ -> .y4m -> yuvkineco -> .ffv1...
    frame=150919 fps=147 q=-0.0 Lsize=17885168kB time=01:44:54.53 bitrate=23276.6kbits/s speed=6.11x

During analysis of the movie, mmdemux determined that it had a 23.976fps
23pulldown field order. It then used yuvkineco to make it progressive and much more
compatible.

    cropdetect |################################| 100.0% time=300.0/300.0 fps=734.00 remaining=0s crop=720:362:0:56

Further analysis determine that cropping to 720x362 (from 720x480) would get
rid of top and bottom black bars to save some space in the output file.
Cropping happens during the following re-compression to VP9 format:

    2021-01-01 00:00:00 INFO Convert .ffv1.mkv -> track-00-video.yuvkineco-pullup.vp9.ivf w/ ffmpeg...
    [ffmpeg-2pass-pipe] PASS 1
    frame=150919 fps=114 q=0.0 Lsize=       0kB time=00:00:00.00 bitrate=N/A speed=   0x
    Output file is empty, nothing was encoded
    [ffmpeg-2pass-pipe] PASS 2
    frame=150919 fps= 11 q=0.0 Lsize=  419875kB time=01:44:54.57 bitrate= 546.4kbits/s speed=0.458x

Now that the video stream is converted, mmdemux moves to the audio streams and
converts them to Vorbis/Opus format:

    [ac3 @ 0x5572701e8140] Estimating duration from bitrate, this may be inaccurate
    2021-01-01 00:00:00 INFO Convert .ac3 -> track-01-audio.eng.wav w/ ffmpeg...
    size= 7081416kB time=01:44:54.59 bitrate=9216.0kbits/s speed=41.2x
    [wav @ 0x556756645140] Ignoring maximum wav data size, file may be invalid
    [wav @ 0x556756645140] Estimating duration from bitrate, this may be inaccurate
    2021-01-01 00:00:00 INFO Convert .wav -> track-01-audio.eng.opus.ogg w/ opusenc...
    WARNING: WAV file uses side surround instead of rear for 5.1;
    remapping side speakers to rear in encoding.
    Skipping chunk of type "LIST", length 26
    Encoding using libopus 1.3.1 (audio)
    -----------------------------------------------------
       Input: 48kHz 6 channels
      Output: 6 channels (4 coupled, 2 uncoupled)
	      20ms packets, 448kbit/sec VBR
     Preskip: 312

    [|] 01:44:27.56 34.6x realtime, 359.9kbit/s

    Encoding complete
    -----------------------------------------------------
	   Encoded: 1 hour, 44 minutes, and 54.6 seconds
	   Runtime: 3 minutes and 1 seconds
		    (34.78x realtime)
	     Wrote: 285081411 bytes, 314730 packets, 6321 pages
	   Bitrate: 360.485kbit/s (without overhead)
     Instant rates: 180.4kbit/s to 876.4kbit/s
		    (451 to 2191 bytes per packet)
	  Overhead: 0.506% (container+metadata)

    [ac3 @ 0x555c971c5140] Estimating duration from bitrate, this may be inaccurate
    2021-01-01 00:00:00 INFO Convert .ac3 -> track-02-audio.eng.wav w/ ffmpeg...
    size= 2360472kB time=01:44:54.59 bitrate=3072.0kbits/s speed= 116x
    [wav @ 0x55cd6f019140] Ignoring maximum wav data size, file may be invalid
    [wav @ 0x55cd6f019140] Estimating duration from bitrate, this may be inaccurate
    2021-01-01 00:00:00 INFO Convert .wav -> track-02-audio.eng.opus.ogg w/ opusenc...
    Skipping chunk of type "LIST", length 26
    Encoding using libopus 1.3.1 (audio)
    -----------------------------------------------------
       Input: 48kHz 2 channels
      Output: 2 channels (2 coupled)
	      20ms packets, 192kbit/sec VBR
     Preskip: 312

    [\] 01:44:50.58 65.5x realtime, 190.2kbit/s

    Encoding complete
    -----------------------------------------------------
	   Encoded: 1 hour, 44 minutes, and 54.6 seconds
	   Runtime: 1 minute and 36 seconds
		    (65.57x realtime)
	     Wrote: 150537796 bytes, 314730 packets, 6297 pages
	   Bitrate: 190.181kbit/s (without overhead)
     Instant rates: 104.8kbit/s to 388.8kbit/s
		    (262 to 972 bytes per packet)
	  Overhead: 0.597% (container+metadata)

    [ac3 @ 0x55c01bdfa140] Estimating duration from bitrate, this may be inaccurate
    2021-01-01 00:00:00 INFO Convert .ac3 -> track-03-audio.eng.wav w/ ffmpeg...
    size= 2360472kB time=01:44:54.59 bitrate=3072.0kbits/s speed= 120x
    [wav @ 0x5620e12c0140] Ignoring maximum wav data size, file may be invalid
    [wav @ 0x5620e12c0140] Estimating duration from bitrate, this may be inaccurate
    2021-01-01 00:00:00 INFO Convert .wav -> track-03-audio.eng.opus.ogg w/ opusenc...
    Skipping chunk of type "LIST", length 26
    Encoding using libopus 1.3.1 (audio)
    -----------------------------------------------------
       Input: 48kHz 2 channels
      Output: 2 channels (2 coupled)
	      20ms packets, 192kbit/sec VBR
     Preskip: 312

    [|] 01:43:35.30 66.8x realtime, 171.9kbit/s

    Encoding complete
    -----------------------------------------------------
	   Encoded: 1 hour, 44 minutes, and 54.6 seconds
	   Runtime: 1 minute and 33 seconds
		    (67.68x realtime)
	     Wrote: 136279528 bytes, 314730 packets, 6297 pages
	   Bitrate: 172.104kbit/s (without overhead)
     Instant rates: 101.6kbit/s to 385.6kbit/s
		    (254 to 964 bytes per packet)
	  Overhead: 0.634% (container+metadata)

    [ac3 @ 0x55739bf5f140] Estimating duration from bitrate, this may be inaccurate
    2021-01-01 00:00:00 INFO Convert .ac3 -> track-04-audio.fra.wav w/ ffmpeg...
    size= 7081416kB time=01:44:54.59 bitrate=9216.0kbits/s speed=39.6x
    [wav @ 0x56207a2f7140] Ignoring maximum wav data size, file may be invalid
    [wav @ 0x56207a2f7140] Estimating duration from bitrate, this may be inaccurate
    2021-01-01 00:00:00 INFO Convert .wav -> track-04-audio.fra.opus.ogg w/ opusenc...
    WARNING: WAV file uses side surround instead of rear for 5.1;
    remapping side speakers to rear in encoding.
    Skipping chunk of type "LIST", length 26
    Encoding using libopus 1.3.1 (audio)
    -----------------------------------------------------
       Input: 48kHz 6 channels
      Output: 6 channels (4 coupled, 2 uncoupled)
	      20ms packets, 384kbit/sec VBR
     Preskip: 312

    [|] 01:44:50.34 28.5x realtime, 310.1kbit/s

    Encoding complete
    -----------------------------------------------------
	   Encoded: 1 hour, 44 minutes, and 54.6 seconds
	   Runtime: 3 minutes and 41 seconds
		    (28.48x realtime)
	     Wrote: 245349554 bytes, 314730 packets, 6298 pages
	   Bitrate: 310.183kbit/s (without overhead)
     Instant rates: 150.8kbit/s to 752kbit/s
		    (377 to 1880 bytes per packet)
	  Overhead: 0.526% (container+metadata)

Audio streams are done. Now mmdemux moves on to subtitles. Given the
`--external-subtitles=non-forced` argument, the 2 non-forced subtitle tracks
are left untouched but the forced subtitle track needs to be converted to
WebVTT format. However, because human intervention is required for this take
and that batch mode is in effect, mmdemux only emits a warning:

    2021-01-01 00:00:00 WARNING BATCH MODE SKIP: Stream #7 .sub -> track-07-subtitle.fra.srt

All automated steps are done and mmdemux exists reminding you that a task was skipped.

    2021-01-01 00:00:00 ERROR Exception: BATCH MODE SKIP: 1 task(s) skipped.

Final manual steps using interactive mode
-----------------------------------------

Let's run it again without `--batch` to complete the leftover task:

    $ mmdemux --mux TheAmerican/title_t00.mkv --chain --external-subtitles=non-forced --interactive
    2021-01-01 00:00:00 INFO Muxing TheAmerican/title_t00.mkv...
    2021-01-01 00:00:00 WARNING Directory exists: TheAmerican/title_t00; Just chaining
    2021-01-01 00:00:00 INFO Optimizing TheAmerican/title_t00...

mmdemux launches SubtitleEdit which will guide you in running OCR over the
forced subtitle track. When done, save it to SubRip (.srt) format and mmdemux
will finish conversion to it's final WebVTT format:

    2021-01-01 00:00:00 WARNING Invoking SubtitleEdit: Please run OCR and save as SubRip (.srt) format: TheAmerican/title_t00/track-07-subtitle.fra.srt
    2021-01-01 00:00:00 INFO Convert .sub -> track-07-subtitle.fra.srt w/ SubtitleEdit...
    cat: /proc/8/status: No such file or directory
    2021-01-01 00:00:00 INFO Convert .srt -> track-07-subtitle.fra.vtt w/ ffmpeg...
    size=       2kB time=01:20:00.29 bitrate=   0.0kbits/s speed=6.57e+06x

Next step, the `--demux` action, is to put it all back together but streams
with duplicate information still need to be examined and categorized:

    2021-01-01 00:00:00 INFO Demuxing TheAmerican/title_t00...

    Stream #2 characteristics already seen: ('audio', IsoLang('eng'))
    audio stream #2: title=None, language=eng, disposition=(), ext=.ac3
    mmdemux(seen)> print

      Index     Codec                              Original       Size        Extension    Language    Title  Disposition
    -------  --------  ------------------------------------  ---------  ---------------  ----------  -------  -------------
	  0  video     mpeg2video, Main, 720x480, 279:157    429951907  .mp2v->.vp9.ivf  und
	  1  audio     ac3, 5.1(side), 448kbps, 48kHz, fltp  285081411  .ac3->.opus.ogg  eng                  default
	 *2  audio     ac3, stereo, 192kbps, 48kHz, fltp     150537796  .ac3->.opus.ogg  eng
	  3  audio     ac3, stereo, 192kbps, 48kHz, fltp     136279528  .ac3->.opus.ogg  eng
	  4  audio     ac3, 5.1(side), 384kbps, 48kHz, fltp  245349554  .ac3->.opus.ogg  fra
	  5  subtitle  dvd_subtitle                            1808384  .sub             eng                  default, *568
	  6  subtitle  dvd_subtitle                            1632256  .sub             fra                  *505
	  7  subtitle  dvd_subtitle                               2075  .sub->.vtt       fra                  forced, *40

This the second English (eng) audio stream, let's "open" it to listen:

    audio stream #2: title=None, language=eng, disposition=(), ext=.ac3
    mmdemux(seen)> open

It is a sound track for the visually impaired. You can tag it as such:

    audio stream #2: title=None, language=eng, disposition=(), ext=.ac3
    mmdemux(seen)> visual_impaired
    audio stream #2: title=None, language=eng, disposition=(visual_impaired), ext=.ac3
    mmdemux(seen)> print

      Index     Codec                              Original       Size        Extension    Language    Title  Disposition
    -------  --------  ------------------------------------  ---------  ---------------  ----------  -------  ---------------
	  0  video     mpeg2video, Main, 720x480, 279:157    429951907  .mp2v->.vp9.ivf  und
	  1  audio     ac3, 5.1(side), 448kbps, 48kHz, fltp  285081411  .ac3->.opus.ogg  eng                  default
	 *2  audio     ac3, stereo, 192kbps, 48kHz, fltp     150537796  .ac3->.opus.ogg  eng                  visual_impaired
	  3  audio     ac3, stereo, 192kbps, 48kHz, fltp     136279528  .ac3->.opus.ogg  eng
	  4  audio     ac3, 5.1(side), 384kbps, 48kHz, fltp  245349554  .ac3->.opus.ogg  fra
	  5  subtitle  dvd_subtitle                            1808384  .sub             eng                  default, *568
	  6  subtitle  dvd_subtitle                            1632256  .sub             fra                  *505
	  7  subtitle  dvd_subtitle                               2075  .sub->.vtt       fra                  forced, *40

I'm personally not interested in keeping this type of track. Let's so I just
instruct mmdemux to have it skipped and not included in the final movie file:

    audio stream #2: title=None, language=eng, disposition=(visual_impaired), ext=.ac3
    mmdemux(seen)> skip

There's still another English audio track. Opening it reveals a director's
commentary, so let's set the title and tag it as a commentary:

    Stream #3 characteristics already seen: ('audio', IsoLang('eng'))
    audio stream #3: title=None, language=eng, disposition=(), ext=.ac3
    mmdemux(seen)> open
    audio stream #3: title=None, language=eng, disposition=(), ext=.ac3
    mmdemux(seen)> title "Director Commentary"
    audio stream #3: title='Director Commentary', language=eng, disposition=(), ext=.ac3
    mmdemux(seen)> comment
    audio stream #3: title='Director Commentary', language=eng, disposition=(comment), ext=.ac3
    mmdemux(seen)> print

      Index     Codec                              Original       Size        Extension    Language                Title  Disposition
    -------  --------  ------------------------------------  ---------  ---------------  ----------  -------------------  ---------------
	  0  video     mpeg2video, Main, 720x480, 279:157    429951907  .mp2v->.vp9.ivf  und
	  1  audio     ac3, 5.1(side), 448kbps, 48kHz, fltp  285081411  .ac3->.opus.ogg  eng                              default
       (S)2  audio     ac3, stereo, 192kbps, 48kHz, fltp     150537796  .ac3->.opus.ogg  eng                              visual_impaired
	  4  audio     ac3, 5.1(side), 384kbps, 48kHz, fltp  245349554  .ac3->.opus.ogg  fra
	 *3  audio     ac3, stereo, 192kbps, 48kHz, fltp     136279528  .ac3->.opus.ogg  eng         Director Commentary  comment
	  5  subtitle  dvd_subtitle                            1808384  .sub             eng                              default, *568
	  6  subtitle  dvd_subtitle                            1632256  .sub             fra                              *505
	  7  subtitle  dvd_subtitle                               2075  .sub->.vtt       fra                              forced, *40
    audio stream #3: title='Director Commentary', language=eng, disposition=(comment), ext=.ac3
    mmdemux(seen)> continue

Other subtitle streams will not be converted due to
`--external-subtitles=non-forced` so they are exported as external files:

    2021-01-01 00:00:00 WARNING Stream #5 track-05-subtitle.eng.sub -> TheAmerican/title_t00.demux.eng.sub
    2021-01-01 00:00:00 WARNING Stream #5 track-05-subtitle.eng.idx -> TheAmerican/title_t00.demux.eng.idx
    2021-01-01 00:00:00 WARNING Stream #6 track-06-subtitle.fra.sub -> TheAmerican/title_t00.demux.fra.sub
    2021-01-01 00:00:00 WARNING Stream #6 track-06-subtitle.fra.idx -> TheAmerican/title_t00.demux.fra.idx

mmdemux continues with merging all the converted video, audio, subtitle tracks
and chapters together and doing final tagging:

    Encap video stream 0 w/ ffmpeg |                                | 0.0% time=6294.5/179135927.6 fps=140347.00 remaining=30315s
    2021-01-01 00:00:00 INFO Merge w/ ffmpeg...
    Merge w/ ffmpeg |                                | 0.0% time=6294.6/179135927.6 fps=27604.00 remaining=225440s
    2021-01-01 00:00:00 INFO Add chapters w/ mkvpropedit...
    The file is being analyzed.
    The changes are written to the file.
    Done.
    2021-01-01 00:00:00 INFO Editing TheAmerican/title_t00.demux.webm...
    2021-01-01 00:00:00 INFO DONE writing TheAmerican/title_t00.demux.webm

The `--verify` action is then performed:

    2021-01-01 00:00:00 INFO Verifying TheAmerican/title_t00.demux.webm...
    2021-01-01 00:00:00 INFO Muxing TheAmerican/title_t00.demux.webm...
    2021-01-01 00:00:00 INFO Extract video stream #0: track-00-video.vp9.ivf
    2021-01-01 00:00:00 INFO Extract track #0 w/ ffmpeg...
    Extract video track 0 w/ ffmpeg |############################### | 100.0% time=6294.5/6294.6 fps=145068.00 remaining=1s
    2021-01-01 00:00:00 INFO Will extract audio stream #1 w/ mkvextract: track-01-audio.eng.opus.ogg
    2021-01-01 00:00:00 INFO Will extract audio stream #2 w/ mkvextract: track-02-audio.fra.opus.ogg
    2021-01-01 00:00:00 INFO Will extract audio stream #3 w/ mkvextract: track-03-audio.eng.opus.ogg
    2021-01-01 00:00:00 WARNING Correcting subtitle stream #4 start time -0.007s to 0 based on experience
    2021-01-01 00:00:00 WARNING Not muxing subtitle stream #4...
    2021-01-01 00:00:00 INFO Extract tracks w/ mkvextract...
    Extracting track 1 with the CodecID 'A_OPUS' to the file 'TheAmerican/title_t00.demux/track-01-audio.eng.opus.ogg'. Container format: Ogg (Opus in Ogg)
    Extracting track 2 with the CodecID 'A_OPUS' to the file 'TheAmerican/title_t00.demux/track-02-audio.fra.opus.ogg'. Container format: Ogg (Opus in Ogg)
    Extracting track 3 with the CodecID 'A_OPUS' to the file 'TheAmerican/title_t00.demux/track-03-audio.eng.opus.ogg'. Container format: Ogg (Opus in Ogg)
    Progress: 100%

      Index     Codec                              Original       Size    Extension    Language                Title  Disposition
    -------  --------  ------------------------------------  ---------  -----------  ----------  -------------------  ---------------
	  0  video     vp9, Profile 0, 720x362, 66960:28417  429951907  .vp9.ivf     und                              default
	  1  audio     opus, 5.1, 48kHz, fltp                286584265  .opus.ogg    eng                              default
	  2  audio     opus, 5.1, 48kHz, fltp                246642699  .opus.ogg    fra
	  3  audio     opus, stereo, 48kHz, fltp             136954454  .opus.ogg    eng         Director Commentary
	  4  subtitle  webvtt                                           .vtt         fra                              default, forced

    File                                                       Start time    Duration    Total time
    -------------------------------------------------------  ------------  ----------  ------------
    TheAmerican/title_t00.demux/track-00-video.vp9.ivf                  0     6294.58       6294.58
    TheAmerican/title_t00.demux/track-01-audio.eng.opus.ogg             0      6294.6        6294.6
    TheAmerican/title_t00.demux/track-02-audio.fra.opus.ogg             0      6294.6        6294.6
    TheAmerican/title_t00.demux/track-03-audio.eng.opus.ogg             0      6294.6        6294.6
    2021-01-01 00:00:00 INFO Cleaning up TheAmerican/title_t00.demux
    2021-01-01 00:00:00 INFO DONE writing & verifying TheAmerican/title_t00.demux.webm

Everything checks out!

If there were any mistakes during conversion mmdemux would hopefully have found
them here, such as video and audio being out of sync by more than 5 seconds.

    $ ls -lv TheAmerican/
    total 7605568
    drwxr-xr-x 2 qip qip       4096 Jan  1 00:00 title_t00
    -rw-r--r-- 1 qip qip      25521 Jan  1 00:00 title_t00.demux.eng.idx
    -rw-r--r-- 1 qip qip    1808384 Jan  1 00:00 title_t00.demux.eng.sub
    -rw-r--r-- 1 qip qip      22749 Jan  1 00:00 title_t00.demux.fra.idx
    -rw-r--r-- 1 qip qip    1632256 Jan  1 00:00 title_t00.demux.fra.sub
    -rw-r--r-- 1 qip qip 1098957090 Jan  1 00:00 title_t00.demux.webm
    -rw-rw-rw- 1 qip qip 6685628715 Jan  1 00:00 title_t00.mkv

Let's use ffmpeg/ffprobe to dump the content of the output movie file,
`TheAmerican/title_t00.demux.webm`:

    $ ffprobe -i TheAmerican/title_t00.demux.webm
    ffprobe version 4.3.1 Copyright (c) 2007-2020 the FFmpeg developers
      built with gcc 10 (Debian 10.2.1-1)
      configuration: --disable-decoder=amrnb --disable-decoder=libopenjpeg --disable-gnutls --disable-libopencv --disable-podpages --disable-sndio --disable-stripping --enable-avfilter --enable-avresample --enable-gcrypt --enable-gpl --enable-ladspa --enable-libaom --enable-libaribb24 --enable-libass --enable-libbluray --enable-libbs2b --enable-libcaca --enable-libcdio --enable-libcodec2 --enable-libdav1d --enable-libfdk-aac --enable-libflite --enable-libfontconfig --enable-libfreetype --enable-libfribidi --enable-libgme --enable-libgsm --enable-libilbc --enable-libjack --enable-libkvazaar --enable-liblensfun --enable-libmp3lame --enable-libmysofa --enable-libopencore-amrnb --enable-libopencore-amrwb --enable-libopenh264 --enable-libopenjpeg --enable-libopenmpt --enable-libopus --enable-libpulse --enable-librabbitmq --enable-librsvg --enable-librubberband --enable-libshine --enable-libsnappy --enable-libsoxr --enable-libspeex --disable-libsrt --enable-libtesseract --enable-libtheora --enable-libtwolame --enable-libvidstab --enable-libvo-amrwbenc --enable-libvorbis --enable-libvpx --enable-libwavpack --enable-libwebp --enable-libwebp --enable-libx265 --enable-libxml2 --enable-libxvid --enable-libzimg --enable-libzmq --enable-libzvbi --enable-lv2 --enable-nonfree --enable-openal --enable-opencl --enable-opengl --enable-openssl --enable-postproc --enable-pthreads --enable-shared --enable-version3 --enable-vulkan --incdir=/usr/include/x86_64-linux-gnu --libdir=/usr/lib/x86_64-linux-gnu --prefix=/usr --toolchain=hardened --enable-frei0r --enable-chromaprint --enable-libx264 --enable-libiec61883 --enable-libdc1394 --enable-vaapi --enable-libmfx --enable-libvmaf --disable-altivec --shlibdir=/usr/lib/x86_64-linux-gnu
      libavutil      56. 51.100 / 56. 51.100
      libavcodec     58. 91.100 / 58. 91.100
      libavformat    58. 45.100 / 58. 45.100
      libavdevice    58. 10.100 / 58. 10.100
      libavfilter     7. 85.100 /  7. 85.100
      libavresample   4.  0.  0 /  4.  0.  0
      libswscale      5.  7.100 /  5.  7.100
      libswresample   3.  7.100 /  3.  7.100
      libpostproc    55.  7.100 / 55.  7.100
    Input #0, matroska,webm, from 'TheAmerican/title_t00.demux.webm':
      Metadata:
	title           : The American
	encoder         : Lavf58.45.100
	MOVIE/TITLE-eng : The American
	MOVIE/ENCODER-eng: Lavf58.45.100
	MOVIE/DATE_RELEASED-eng: 2021-01-01
	MOVIE/ORIGINAL_MEDIA_TYPE-eng: DVD
      Duration: 01:44:54.60, start: -0.007000, bitrate: 1396 kb/s
	Chapter #0:0: start 0.000000, end 361.694667
	Metadata:
	  title           : Chapter 01
	Chapter #0:1: start 361.694667, end 804.336867
	Metadata:
	  title           : Chapter 02
	Chapter #0:2: start 804.336867, end 1186.218367
	Metadata:
	  title           : Chapter 03
	Chapter #0:3: start 1186.218367, end 1520.635783
	Metadata:
	  title           : Chapter 04
	Chapter #0:4: start 1520.635783, end 1733.932200
	Metadata:
	  title           : Chapter 05
	Chapter #0:5: start 1733.932200, end 2115.947167
	Metadata:
	  title           : Chapter 06
	Chapter #0:6: start 2115.947167, end 2470.634833
	Metadata:
	  title           : Chapter 07
	Chapter #0:7: start 2470.634833, end 2691.722367
	Metadata:
	  title           : Chapter 08
	Chapter #0:8: start 2691.722367, end 3029.693333
	Metadata:
	  title           : Chapter 09
	Chapter #0:9: start 3029.693333, end 3351.047700
	Metadata:
	  title           : Chapter 10
	Chapter #0:10: start 3351.047700, end 3562.675783
	Metadata:
	  title           : Chapter 11
	Chapter #0:11: start 3562.675783, end 3878.541333
	Metadata:
	  title           : Chapter 12
	Chapter #0:12: start 3878.541333, end 4076.872800
	Metadata:
	  title           : Chapter 13
	Chapter #0:13: start 4076.872800, end 4502.865033
	Metadata:
	  title           : Chapter 14
	Chapter #0:14: start 4502.865033, end 4808.003200
	Metadata:
	  title           : Chapter 15
	Chapter #0:15: start 4808.003200, end 5014.309300
	Metadata:
	  title           : Chapter 16
	Chapter #0:16: start 5014.309300, end 5476.838033
	Metadata:
	  title           : Chapter 17
	Chapter #0:17: start 5476.838033, end 5696.807783
	Metadata:
	  title           : Chapter 18
	Chapter #0:18: start 5696.807783, end 5975.085783
	Metadata:
	  title           : Chapter 19
	Chapter #0:19: start 5975.085783, end 6294.621667
	Metadata:
	  title           : Chapter 20
	Stream #0:0: Video: vp9 (Profile 0), yuv420p(tv), 720x362, SAR 186:157 DAR 66960:28417, 23.98 fps, 23.98 tbr, 1k tbn, 1k tbc (default)
	Stream #0:1(eng): Audio: opus, 48000 Hz, 5.1, fltp (default)
	Stream #0:2(fra): Audio: opus, 48000 Hz, 5.1, fltp
	Stream #0:3(eng): Audio: opus, 48000 Hz, stereo, fltp
	Metadata:
	  title           : Director Commentary
	Stream #0:4(fra): Subtitle: webvtt (default) (forced)

Perfectly compatible and standard WebM movie file with progressive VP9 video,
multiple Opus audio tracks, WebVTT subtitles, and chapters as well as proper
metadata tagging for title, release date and original media type.

Organize in your media library
------------------------------

Now you're ready to move these files to your media library folders.

How about using organize-media? It will use the movie's metadata tags to rename
it (and any auxiliary/external files) according to the rules of your preferred
media library database application:

    $ organize-media TheAmerican/title_t00.demux.webm
    2021-01-01 00:00:00 INFO Organizing TheAmerican/title_t00.demux.webm...
    2021-01-01 00:00:00 INFO   Create /nfs/media1/Movies/The American (2010).
    2021-01-01 00:00:00 INFO   Rename to /nfs/media1/Movies/The American (2010)/The American (2010).webm.
    Copying |################################| 100% (1.02GB) 611.35MB/s 0:00:00
    2021-01-01 00:00:00 INFO   Rename aux /nfs/media1/Movies/The American (2010)/The American (2010).eng.idx.
    Copying |################################| 100% (24.92KB) 253.45MB/s 0:00:00
    2021-01-01 00:00:00 INFO   Rename aux /nfs/media1/Movies/The American (2010)/The American (2010).eng.sub.
    Copying |################################| 100% (1.72MB) 679.57MB/s 0:00:00
    2021-01-01 00:00:00 INFO   Rename aux /nfs/media1/Movies/The American (2010)/The American (2010).fra.idx.
    Copying |################################| 100% (22.22KB) 393.10MB/s 0:00:00
    2021-01-01 00:00:00 INFO   Rename aux /nfs/media1/Movies/The American (2010)/The American (2010).fra.sub.
    Copying |################################| 100% (1.56MB) 914.87MB/s 0:00:00

Tips
====

Setting default options 
-----------------------

There are many available options to tweak conversion to your needs.
All options can be specified in `~/.config/mmdemux/config` so they become the
defaults for your workflow.

Here are my defaults:

    $ cat ~/.config/mmdemux/config
    [options]
    ocr-subtitles=forced
    external-subtitles=non-forced
    eject
    beep
    crop
    auto-verify
    nice=10
    ionice=7
    parallel-chapters
    slurm
    #cuda
    preferred-broadcast-format=NTSC
    rip-languages=eng fra und

    $ cat ~/.config/organize-media/config
    [default-output]
    audiobook = /nfs/media1/Audiobooks/
    movie = /nfs/media1/Movies/
    musicvideo = /nfs/media1/MusicVideos/
    normal = /nfs/media1/Music
    tvshow = /nfs/media1/TV Shows/

