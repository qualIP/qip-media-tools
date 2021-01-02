%module libdvdread_swig

%{
#define SWIG_FILE_WITH_INIT
%}

%include cpointer.i
%include stdint.i
%include typemaps.i

%{
#include <dvdread/dvd_reader.h>
%}
%include <dvdread/dvd_reader.h>

%{
#include <dvdread/ifo_types.h>
%}
%include "/usr/include/dvdread/ifo_types.h"

%{
#include <dvdread/ifo_read.h>
%}
%include "/usr/include/dvdread/ifo_read.h"

%extend pgc_t { uint16_t get_audio_control(int i) { return $self->audio_control[i]; } }
%extend pgc_t { uint32_t get_subp_control(int i) { return $self->subp_control[i]; } }
%extend pgc_t { uint32_t get_palette(int i) { return $self->palette[i]; } }
%extend pgc_t { uint8_t get_program_map(int i) { return $self->program_map[i]; } }
%extend pgc_t { cell_playback_t * get_cell_playback(int i) { return &$self->cell_playback[i]; } }
%extend vtsi_mat_t { subp_attr_t * get_vts_subp_attr(int i) { return &$self->vts_subp_attr[i]; } }
%extend vtsi_mat_t { audio_attr_t * get_vts_audio_attr(int i) { return &$self->vts_audio_attr[i]; } }
%extend pgcit_t { pgci_srp_t *get_pgci_srp(int i) { return &$self->pgci_srp[i]; } }
%extend ttu_t { ptt_info_t * get_ptt(int i) { return &$self->ptt[i]; } }
%extend vts_ptt_srpt_t { ttu_t * get_title(int i) { return &$self->title[i]; } }
%extend tt_srpt_t { title_info_t * get_title(int i) { return &$self->title[i]; } }
%extend pgci_ut_t { pgci_lu_t * get_lu(int i) { return &$self->lu[i]; } }

PyObject *wrapDVDReadBlocks(dvd_file_t *dvd_file, int offset, size_t block_count);


%{
PyObject *wrapDVDReadBlocks(dvd_file_t *dvd_file, int offset, size_t block_count) {
    PyObject *buf = PyBytes_FromStringAndSize(
        NULL, block_count * DVD_VIDEO_LB_LEN);
    if (!buf) {
        return NULL;
    }
    ssize_t nRead = DVDReadBlocks(dvd_file, offset, block_count,
                                  (unsigned char *)PyBytes_AS_STRING(buf));
    if (nRead < 0) {
        Py_CLEAR(buf);
        return PyErr_SetFromErrno(PyExc_IOError);
    }
    if ((size_t)nRead < block_count) {
        _PyBytes_Resize(&buf, nRead * DVD_VIDEO_LB_LEN);
    }
    return buf;
}
%}

// vim: ft=c
