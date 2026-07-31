; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; fileio.s - AmigaDOS file I/O wrappers for HAS runtime (Motorola 68000)
;
; Design:
; - Thin wrappers around dos.library Open/Close/Read/Write/Seek.
; - dos.library base is managed explicitly with FileIoInit/FileIoDone.
; - Intended usage in takeover-based programs:
;   1) call ReleaseSystem()
;   2) perform FileIo* calls
;   3) call TakeSystem()
;
; Calling convention:
; - All routines use link a6,#0 and stack args at 8(a6), 12(a6), ...
; - Returns in d0 unless stated otherwise.
;
; Public API:
;   FileIoInit() -> int          ; 0 success, -1 fail
;   FileIoDone() -> int          ; 0 always (idempotent)
;   FileIoErr() -> int           ; IoErr() value, -1 if DOS not initialized
;   FileOpen(path, mode) -> int  ; file handle (BPTR) or 0
;   FileClose(handle) -> int     ; DOS result
;   FileRead(handle, buf, len) -> int   ; bytes read or -1
;   FileWrite(handle, buf, len) -> int  ; bytes written or -1
;   FileSeek(handle, pos, mode) -> int  ; old pos or -1
;   FileDelete(path) -> int      ; DOSTRUE(-1)/DOSFALSE(0)
;   FileRename(old_path, new_path) -> int ; DOSTRUE(-1)/DOSFALSE(0)
;   FileLock(path, mode) -> int  ; lock BPTR or 0
;   FileUnLock(lock) -> void
;   FileExamine(lock, fib) -> int ; DOSTRUE(-1)/DOSFALSE(0)
;
; =============================================================================

    include "hardware.i"
    include "exec_lib.i"

    SECTION fileio_data,DATA

FILEIO_DOS_LVO_OPEN      EQU -30
FILEIO_DOS_LVO_CLOSE     EQU -36
FILEIO_DOS_LVO_READ      EQU -42
FILEIO_DOS_LVO_WRITE     EQU -48
FILEIO_DOS_LVO_SEEK      EQU -66
FILEIO_DOS_LVO_DELETE    EQU -72
FILEIO_DOS_LVO_RENAME    EQU -78
FILEIO_DOS_LVO_LOCK      EQU -84
FILEIO_DOS_LVO_UNLOCK    EQU -90
FILEIO_DOS_LVO_EXAMINE   EQU -102
FILEIO_DOS_LVO_IOERR     EQU -132

fileio_dos_name:
    dc.b "dos.library",0
    even

fileio_dos_base:
    dc.l 0

    SECTION fileio_code,CODE

    XDEF FileIoInit
    XDEF FileIoDone
    XDEF FileIoErr
    XDEF FileOpen
    XDEF FileClose
    XDEF FileRead
    XDEF FileWrite
    XDEF FileSeek
    XDEF FileDelete
    XDEF FileRename
    XDEF FileLock
    XDEF FileUnLock
    XDEF FileExamine

; -----------------------------------------------------------------------------
; Function: FileIoInit
; Input: none
; Output: d0=0 success, d0=-1 failure
; Description: Opens dos.library once and caches its base.
; Notes: Safe to call multiple times; repeated success is a no-op.
; -----------------------------------------------------------------------------
FileIoInit:
    link a6,#0
    movem.l d1-d2/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    bne .ok

    move.l ExecBase,a6
    lea fileio_dos_name,a1
    jsr _LVOOldOpenLibrary(a6)
    move.l d0,fileio_dos_base
    tst.l d0
    bne .ok

    moveq #-1,d0
    bra .done

.ok:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d2/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileIoDone
; Input: none
; Output: d0=0
; Description: Closes dos.library if currently open.
; Notes: Idempotent; calling when not initialized is harmless.
; -----------------------------------------------------------------------------
FileIoDone:
    link a6,#0
    movem.l d1-d2/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .done

    move.l d0,a1
    move.l ExecBase,a6
    jsr _LVOCloseLibrary(a6)
    clr.l fileio_dos_base

.done:
    moveq #0,d0
    movem.l (sp)+,d1-d2/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileIoErr
; Input: none
; Output: d0=IoErr(), d0=-1 if DOS is not initialized
; Description: Returns last dos.library error code.
; Notes: Call immediately after a failed File* operation for accurate code.
; -----------------------------------------------------------------------------
FileIoErr:
    link a6,#0
    movem.l d1-d2/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    bne .has_dos

    moveq #-1,d0
    bra .done

.has_dos:
    move.l d0,a6
    jsr FILEIO_DOS_LVO_IOERR(a6)

.done:
    movem.l (sp)+,d1-d2/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileOpen
; Input: 8(a6)=path_ptr, 12(a6)=mode
; Output: d0=file handle (BPTR) or 0 on failure
; Description: Opens a file via dos.library Open().
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileOpen:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l d0,a6
    jsr FILEIO_DOS_LVO_OPEN(a6)
    bra .done

.no_dos:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileClose
; Input: 8(a6)=handle
; Output: d0=DOS Close() result
; Description: Closes a previously opened file handle.
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileClose:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l d0,a6
    jsr FILEIO_DOS_LVO_CLOSE(a6)
    bra .done

.no_dos:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileRead
; Input: 8(a6)=handle, 12(a6)=buffer_ptr, 16(a6)=length
; Output: d0=bytes read or -1 on failure
; Description: Reads bytes from file into memory buffer.
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileRead:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l 16(a6),d3
    move.l d0,a6
    jsr FILEIO_DOS_LVO_READ(a6)
    bra .done

.no_dos:
    moveq #-1,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileWrite
; Input: 8(a6)=handle, 12(a6)=buffer_ptr, 16(a6)=length
; Output: d0=bytes written or -1 on failure
; Description: Writes bytes from memory buffer to file.
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileWrite:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l 16(a6),d3
    move.l d0,a6
    jsr FILEIO_DOS_LVO_WRITE(a6)
    bra .done

.no_dos:
    moveq #-1,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileSeek
; Input: 8(a6)=handle, 12(a6)=position, 16(a6)=mode
; Output: d0=previous file position or -1 on failure
; Description: Seeks in file using dos.library Seek().
; Notes: mode is one of OFFSET_BEGINNING(-1), OFFSET_CURRENT(0), OFFSET_END(1).
; -----------------------------------------------------------------------------
FileSeek:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l 16(a6),d3
    move.l d0,a6
    jsr FILEIO_DOS_LVO_SEEK(a6)
    bra .done

.no_dos:
    moveq #-1,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileDelete
; Input: 8(a6)=path_ptr
; Output: d0=DOSTRUE(-1) or DOSFALSE(0)
; Description: Deletes a file by path.
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileDelete:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l d0,a6
    jsr FILEIO_DOS_LVO_DELETE(a6)
    bra .done

.no_dos:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileRename
; Input: 8(a6)=old_path_ptr, 12(a6)=new_path_ptr
; Output: d0=DOSTRUE(-1) or DOSFALSE(0)
; Description: Renames or moves a file path.
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileRename:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l d0,a6
    jsr FILEIO_DOS_LVO_RENAME(a6)
    bra .done

.no_dos:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileLock
; Input: 8(a6)=path_ptr, 12(a6)=mode
; Output: d0=lock BPTR or 0
; Description: Acquires a file lock.
; Notes: mode is DOS_SHARED_LOCK(-2) or DOS_EXCLUSIVE_LOCK(-1).
; -----------------------------------------------------------------------------
FileLock:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l d0,a6
    jsr FILEIO_DOS_LVO_LOCK(a6)
    bra .done

.no_dos:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileUnLock
; Input: 8(a6)=lock BPTR
; Output: none
; Description: Releases a lock obtained via FileLock.
; Notes: Requires FileIoInit() success before use.
; -----------------------------------------------------------------------------
FileUnLock:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .done

    move.l 8(a6),d1
    move.l d0,a6
    jsr FILEIO_DOS_LVO_UNLOCK(a6)

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: FileExamine
; Input: 8(a6)=lock BPTR, 12(a6)=fib_ptr
; Output: d0=DOSTRUE(-1) or DOSFALSE(0)
; Description: Calls Examine(lock, fib).
; Notes: fib_ptr must point to a valid FileInfoBlock.
; -----------------------------------------------------------------------------
FileExamine:
    link a6,#0
    movem.l d1-d3/a0-a6,-(sp)

    move.l fileio_dos_base,d0
    tst.l d0
    beq .no_dos

    move.l 8(a6),d1
    move.l 12(a6),d2
    move.l d0,a6
    jsr FILEIO_DOS_LVO_EXAMINE(a6)
    bra .done

.no_dos:
    moveq #0,d0

.done:
    movem.l (sp)+,d1-d3/a0-a6
    unlk a6
    rts