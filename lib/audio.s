; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; audio.s - HAS ABI wrappers around ptplayer for #import music / #import sound
; =============================================================================
; Provides stack-frame (link a6) entry points for InitAudio / PlayMusic /
; PlaySound / etc. ptplayer APIs expect a6 = CUSTOM ($DFF000); every routine
; here saves the HAS frame pointer to a2 before overwriting a6, and restores
; it before unlk so the stack frame is never corrupted.
;
; Requires XDEF music_table / sfx_table from codegen (#import music|sound →
; build/gen/audio_tables.s). Link dependency: ptplayer.s.
; =============================================================================

    include "hardware.i"

    SECTION audio_code,CODE
    CNOP 0,4

    XDEF InitAudio
    XDEF QuitAudio
    XDEF PlayMusic
    XDEF ChangeMusic
    XDEF StopMusic
    XDEF PauseMusic
    XDEF ResumeMusic
    XDEF PlaySound
    XDEF SetMusicVolume

    XREF music_table
    XREF _mt_install_cia
    XREF _mt_remove_cia
    XREF _mt_init
    XREF _mt_end
    XREF _mt_musicmask
    XREF _mt_mastervol
    XREF _mt_Enable
    XREF play_sfx

; Default master volume applied by PlayMusic / ChangeMusic (0..64).
AUDIO_DEFAULT_MASTER_VOL    EQU 16

; -----------------------------------------------------------------------------
; Function: InitAudio
; Input: none
; Output: none
; Description: Install CIA-B music interrupt (PAL) and reserve channel 0 for
;              music via _mt_musicmask.
; Notes: Call once after TakeSystem (or equivalent). Pair with QuitAudio.
; -----------------------------------------------------------------------------
InitAudio:
    link a6,#0
    movem.l d0/a0/a2,-(sp)
    move.l a6,a2                    ; save HAS frame pointer
    lea CUSTOM,a6
    sub.l a0,a0                     ; VectorBase = 0 (68000)
    moveq #1,d0                     ; PAL
    jsr _mt_install_cia
    lea CUSTOM,a6
    moveq #1,d0                     ; music owns Paula channel 0
    jsr _mt_musicmask
    move.l a2,a6
    movem.l (sp)+,d0/a0/a2
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: QuitAudio
; Input: none
; Output: none
; Description: Stop playback and remove the CIA-B interrupt handler.
; -----------------------------------------------------------------------------
QuitAudio:
    link a6,#0
    movem.l a2,-(sp)
    move.l a6,a2
    lea CUSTOM,a6
    jsr _mt_end
    jsr _mt_remove_cia
    move.l a2,a6
    movem.l (sp)+,a2
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: PlayMusic
; Input: 8(a6)=track_id (long; index into music_table)
; Output: none
; Description: Initialise the MOD at music_table[track_id], enable playback,
;              and set master volume to AUDIO_DEFAULT_MASTER_VOL.
; -----------------------------------------------------------------------------
PlayMusic:
    link a6,#0
    movem.l d0-d1/a0-a2,-(sp)
    move.l a6,a2
    move.l 8(a6),d0                 ; track_id
    lea music_table,a0
    lsl.l #2,d0                     ; index * 4
    add.l d0,a0
    move.l (a0),a0                  ; a0 = module pointer
    lea CUSTOM,a6
    sub.l a1,a1                     ; samples in module
    moveq #0,d0                     ; song position 0
    jsr _mt_init
    move.b #1,_mt_Enable
    lea CUSTOM,a6
    move.w #AUDIO_DEFAULT_MASTER_VOL,d0
    jsr _mt_mastervol
    move.l a2,a6
    movem.l (sp)+,d0-d1/a0-a2
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: ChangeMusic
; Input: 8(a6)=track_id (long)
; Output: none
; Description: Stop current tune then PlayMusic(track_id).
; -----------------------------------------------------------------------------
ChangeMusic:
    link a6,#0
    movem.l d0-d1/a0-a2,-(sp)
    move.l a6,a2
    lea CUSTOM,a6
    jsr _mt_end
    move.l a2,a6                    ; restore frame to re-read arg
    move.l 8(a6),d0
    lea music_table,a0
    lsl.l #2,d0
    add.l d0,a0
    move.l (a0),a0
    lea CUSTOM,a6
    sub.l a1,a1
    moveq #0,d0
    jsr _mt_init
    move.b #1,_mt_Enable
    lea CUSTOM,a6
    move.w #AUDIO_DEFAULT_MASTER_VOL,d0
    jsr _mt_mastervol
    move.l a2,a6
    movem.l (sp)+,d0-d1/a0-a2
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: StopMusic
; Input: none
; Output: none
; Description: Stop MOD playback (_mt_end). SFX are unaffected.
; -----------------------------------------------------------------------------
StopMusic:
    link a6,#0
    movem.l a2,-(sp)
    move.l a6,a2
    lea CUSTOM,a6
    jsr _mt_end
    move.l a2,a6
    movem.l (sp)+,a2
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: PauseMusic
; Input: none
; Output: none
; Description: Clear _mt_Enable so the CIA tick skips music (SFX still play).
; -----------------------------------------------------------------------------
PauseMusic:
    link a6,#0
    clr.b _mt_Enable
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: ResumeMusic
; Input: none
; Output: none
; Description: Set _mt_Enable so music continues from the current position.
; -----------------------------------------------------------------------------
ResumeMusic:
    link a6,#0
    move.b #1,_mt_Enable
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: PlaySound
; Input: 8(a6)=sfx_id (long; index into sfx_table)
; Output: none
; Description: Play a one-shot sound effect via play_sfx (no loop).
; Notes: play_sfx loads CUSTOM itself; frame pointer is still preserved.
; -----------------------------------------------------------------------------
PlaySound:
    link a6,#0
    movem.l d0-d1/a2,-(sp)
    move.l a6,a2
    move.l 8(a6),d0                 ; sfx_id
    moveq #0,d1                     ; no loop
    jsr play_sfx
    move.l a2,a6
    movem.l (sp)+,d0-d1/a2
    unlk a6
    rts

; -----------------------------------------------------------------------------
; Function: SetMusicVolume
; Input: 8(a6)=vol (long; 0..64 master volume)
; Output: none
; Description: Wrapper for _mt_mastervol.
; -----------------------------------------------------------------------------
SetMusicVolume:
    link a6,#0
    movem.l d0/a2,-(sp)
    move.l a6,a2
    move.l 8(a6),d0
    lea CUSTOM,a6
    jsr _mt_mastervol
    move.l a2,a6
    movem.l (sp)+,d0/a2
    unlk a6
    rts
