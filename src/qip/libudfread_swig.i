%module libudfread_swig

%{
#define SWIG_FILE_WITH_INIT
%}

%include cpointer.i
%include stdint.i
%include typemaps.i

%{
#include <udfread/udfread.h>
%}
%include <udfread/udfread.h>


PyObject *wrap_udfread_read_blocks(UDFFILE *udf_file, uint32_t file_block, uint32_t num_blocks, int flags);

%{
PyObject *wrap_udfread_read_blocks(UDFFILE *udf_file, uint32_t file_block, uint32_t num_blocks, int flags) {
    PyObject *buf = PyBytes_FromStringAndSize(
        NULL, num_blocks * UDF_BLOCK_SIZE);
    if (!buf) {
        return NULL;
    }
    ssize_t nRead = udfread_read_blocks(
        udf_file,
        (void *)PyBytes_AS_STRING(buf),
        file_block,
        num_blocks,
        flags);
    if (nRead < 0) {
        Py_CLEAR(buf);
        return PyErr_SetFromErrno(PyExc_IOError);
    }
    if ((size_t)nRead < num_blocks) {
        _PyBytes_Resize(&buf, nRead * UDF_BLOCK_SIZE);
    }
    return buf;
}
%}

PyObject *wrap_udfread_file_read(UDFFILE *udf_file, size_t bytes);

%{
PyObject *wrap_udfread_file_read(UDFFILE *udf_file, size_t bytes) {
    PyObject *buf = PyBytes_FromStringAndSize(
        NULL, bytes);
    if (!buf) {
        return NULL;
    }
    ssize_t nRead = udfread_file_read(
        udf_file,
        (void *)PyBytes_AS_STRING(buf),
        bytes);
    if (nRead < 0) {
        Py_CLEAR(buf);
        return PyErr_SetFromErrno(PyExc_IOError);
    }
    if ((size_t)nRead < bytes) {
        _PyBytes_Resize(&buf, nRead);
    }
    return buf;
}
%}

// vim: ft=c
