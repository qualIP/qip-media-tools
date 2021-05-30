# HOWTO: Ripping a 3D Movie

[![Donate](https://img.shields.io/badge/Donate-PayPal-green.svg)](https://www.paypal.com/biz/fund?id=4CZC3J57FXJVE)

➠ Go back to [qualIP's Media Tools](https://github.com/qualIP/qip-media-tools#qualips-media-tools).

`mmdemux` can be used to rip 3D Blu-ray movies, convert and optimize them to
create VP9/Opus Matroska/WebM files with the 3D video stream still accessible
and encoded in the format of your choice.

Table of Contents:
<!--ts-->
* [HOWTO: Ripping a 3D Movie](#howto-ripping-a-3d-movie)
   * [Step 1: Extract the movie tracks](#step-1-extract-the-movie-tracks)
   * [Step 2: Identify movie tracks to keep](#step-2-identify-movie-tracks-to-keep)
   * [Step 3: Mux, Optimize, Demux, Verify](#step-3-mux-optimize-demux-verify)
<!--te-->

## Step 1: Extract the movie tracks

Use `mmdemux` to extract the movie files. Underneath the hood, MakeMKV is used to read the disk.

Here I want to extract a 3D movie from my Blu-ray drive, `/dev/sr0`.
`--minlength 1m` is used to extract most of the extras too (default: 1h with
`--type movie`, 15m with `--type tvshow`); `--rip-languages eng fra und`
selects to keep only English, French and undefined language tracks.

    $ mmdemux --rip ResidentEvilAfterlife3D --device /dev/sr0 --rip-languages eng fra und --minlength 1m

    2021-01-01 00:00:00 INFO 40 titles saved, 31 skipped.
    2021-01-01 00:00:00 INFO Copy complete. 40 titles saved, 31 skipped.

    2021-01-01 00:00:00 INFO No errors. 40 titles saved

If your DVD/BD disk is difficult to read, you may need to first write an .iso
disk image file (uses gddrescue and can be completed from different drives or
PCs), expand it into an unencrypted backup directory, then extract the movie
files from there.

    $ mmdemux --rip-iso ResidentEvilAfterlife3D.iso --device /dev/sr0
    $ mmdemux --backup ResidentEvilAfterlife3D-backup --device ResidentEvilAfterlife3D.iso
    $ mmdemux --rip ResidentEvilAfterlife3D --device ResidentEvilAfterlife3D-backup --rip-languages eng fra und --minlength 1m

    2021-01-01 00:00:00 INFO 40 titles saved, 31 skipped.
    2021-01-01 00:00:00 INFO Copy complete. 40 titles saved, 31 skipped.

    2021-01-01 00:00:00 INFO No errors. 40 titles saved

FYI, ripping from Blu-ray UHD 3D disks requires a lot of temporary disk space:

    $ du -hsc ResidentEvilAfterlife3D*
    172G    ResidentEvilAfterlife3D
    78G     ResidentEvilAfterlife3D-backup
    4.0K    ResidentEvilAfterlife3D.discatt.dat
    44G     ResidentEvilAfterlife3D.iso
    4.0K    ResidentEvilAfterlife3D.map
    293G    total

    $ ls ResidentEvilAfterlife3D/
    Resident Evil- Afterlife_t00.mkv
    Resident Evil- Afterlife_t01.mkv
    Resident Evil- Afterlife_t02.mkv
    ...
    Resident Evil- Afterlife_t39.mkv

## Step 2: Identify movie tracks to keep

For example, this is the main attraction (largest 32G file), with an MVC-3D encoded H.264 video stream:

    $ cd ResidentEvilAfterlife3D
    $ ls -lh "Resident Evil- Afterlife_t08.mkv"
    -rw-rw-rw- 1 qip qip 30G Jan 01 00:00 Resident Evil- Afterlife_t08.mkv
    $ mmdemux --print "Resident Evil- Afterlife_t08.mkv"
    2021-01-01 00:00:00 INFO Status of ResidentEvilAfterlife3D/Resident Evil- Afterlife_t08.mkv...

      Index      Type                                     Original    Size    Extension    Language    Title  Disposition
    -------  --------  -------------------------------------------  ------  -----------  ----------  -------  ---------------
	  0  video     h264, MVC-3D, High, 8bits, 1920x1080, 16:9           .h264        und
	  1  audio     dts, DTS-HD MA, 5.1(side), 48kHz, s16p(16b)          .dts         eng                  default
	  2  audio     ac3, stereo, 192kbps, 48kHz, fltp                    .ac3         eng
	  3  audio     ac3, stereo, 192kbps, 48kHz, fltp                    .ac3         eng
	  4  audio     ac3, 5.1(side), 448kbps, 48kHz, fltp                 .ac3         fra
	  6  subtitle  hdmv_pgs_subtitle                                    .sup         eng                  default, forced
	  5  subtitle  hdmv_pgs_subtitle                                    .sup         eng
	  7  subtitle  hdmv_pgs_subtitle                                    .sup         eng
	  8  subtitle  hdmv_pgs_subtitle                                    .sup         eng
	  9  subtitle  hdmv_pgs_subtitle                                    .sup         fra
	 11  subtitle  hdmv_pgs_subtitle                                    .sup         fra
	 10  subtitle  hdmv_pgs_subtitle                                    .sup         fra                  forced
	 12  subtitle  hdmv_pgs_subtitle                                    .sup         fra                  forced
	 13  image     mjpeg, cover, 640x360                                .jpg         und                  attached_pic

You can get similar information using `ffprobe` or `mediainfo`; This is just
`mmdemux`'s way of presenting it.

Since this is the main attraction, rename the file with the name of the movie
and the date in parenthesis. **TIP:** Copy-paste the title and year from IMDB.

This renaming helps `mmdemux` to tag the resultant
files with the movie name and date, saving you the trouble of tagging later
(See the `taged` tool).

    mv "Resident Evil- Afterlife_t08.mkv" \
       "Resident Evil: Afterlife (2010).mkv"

Looking at the movie files and perhaps comparing with the menus on a Blu-ray
player, you can identify extras too. Name them with the movie name, as the main
attraction, two dashes, the extra type and then the extra title. For example:

    mv "Resident Evil- Afterlife_t24.mkv" \
       "Resident Evil: Afterlife (2010) -- behindthescenes: New Blood: The Undead of Afterlife.mkv"

Get rid of duplicate tracks, and any clips you don't want.

## Step 3: Mux, Optimize, Demux, Verify

- `--mux`: Split the movie in individual streams.
- `--optimize`: Optimize, convert and re-encode streams.
- `--demux`: Put it all back together.
- `--verify`: Verify the result.

These 4 actions can be executed in order using the `--chain` option.

Since this is a HOWTO about 3D, let's deal with the main feature. Here are the
different options available:

- `None`: Remove the 3D effect -> 2D movie.
- `alternate_frame`: Full resolution left eye frame, then right, ...
- `full_side_by_side`: Full resolution left and right eye images side-by-side in a double-width frame.
- `full_top_and_bottom`: Full resolution left and right eye images on top of each other in a double-height frame.
- `half_side_by_side`: Like full_side_by_side, but half resolution/width (lower quality).
- `half_top_and_bottom`: Like full_top_and_bottom, but half resolution/width (lower quality).
- `hdmi_frame_packing`: Special format from the HDMI 1.4a standard similar to full_top_and_bottom but with an extra band separating them. This is typically a format supported by 3D TVs and projectors.
- `multiview_encoding`: A format of the H.264 codec standard where the left eye image is encoded as usual but with extra information to reconstruct the right eye image from it. This is typically the format found on 3D Blu-ray discsc.

Common abbreviations are supported too (SBS/F-SBS, H-SBS, HDMI, MVC, ...)

The format to choose depends on the equipment you will be using the view the 3D
movie. Check your software and hardware specs for the supported formats.
For example, I host movies in Plex, play them through Kodi on Linux, display
them on an Epson 3D projector. This setup allows me to encode using
`full_side_by_side` mode, without loosing half the pixels, but Kodi will half
the width just before sending to the projector effectively resulting in a
`half_side_by_side` quality. I'm also able to use `bino` with partial success.
It reads the full side-by-side format and sends it out in HDMI frame packing
mode to the projector. This latter method is the best possible quality but
forcing Linux to change the resolution to the special one used by HDMI frame
packing is a bit complicated and unstable.

If you have an NVIDIA GPU, use the `--cuda` option to speed up encoding of
temporary files using GPU-based lossless encoding only; All final encoding is
done using software-only (CPU) encoders that are meant to deliver better
quality (but slower) than their GPU counterparts. Note that most consumer-level
GPUs only allow a single encoding task at a time. If running multiple encodings
at a time, you may not be able to use `--cuda` but, don't worry, the end result
will be the same.

    $ mmdemux --mux "Resident Evil: Afterlife (2010).mkv" --stereo-3d-mode F-SBS --chain --cuda

After hours (or days!) of processing, the demux step will complain of streams
with duplicate characteristics, like multiple English subtitles. Run the same
command in interactive mode and follow the prompts to differentiate them
(comment type, "Director's Commentary" title, etc.)

    $ mmdemux --mux "Resident Evil: Afterlife (2010).mkv" --stereo-3d-mode F-SBS --chain --cuda --interactive

The end result file will have ".demux" in it's name.

I've used some different options here, like `--webm --ocr-subtitles forced
--external-subtitles`. The result is a WebM file with a "Full Side-by-Side" 3D
encoding:

    $ ls -lh "Resident Evil: Afterlife (2010).demux.webm"
    -rw-r--r-- 1 qip qip 2.6G Jan 01 00:00 Resident Evil: Afterlife (2010).demux.webm
    $ mmdemux --print "Resident Evil: Afterlife (2010).demux.webm"
    2021-01-01 00:00:00 INFO Status of Resident Evil: Afterlife (2010).demux.webm...

      Index      Type                         Original    Size    Extension    Language    Title  Disposition
    -------  --------  -------------------------------  ------  -----------  ----------  -------  ---------------
	  0  video     vp9, Profile 0, 3840x1080, 32:9          .vp9.ivf     und                  default
	  1  audio     opus, 5.1, 48kHz, fltp                   .opus.ogg    eng                  default
	  2  audio     opus, 5.1, 48kHz, fltp                   .opus.ogg    fra
	  3  audio     opus, stereo, 48kHz, fltp                .opus.ogg    eng
	  4  subtitle  webvtt                                   .vtt         eng                  default, forced
	  5  subtitle  webvtt                                   .vtt         fra                  forced

The process can be restarted to produce 3D video streams in different formats
or using `--stereo-3d-mode None` to create a non-3D movie using only the left
eye images.

Advanced workflows are possible to save time, using interactive remux,
keeping temporary files for reuse, modifying the `mux.json` file manually, etc.
Also, running using more tasks in parallel with `--jobs --parallel-chapters`,
if your PC has cores to spare, and experimental support exists for sending out the
work to a Slurm cloud. But that's for another HOWTO.
