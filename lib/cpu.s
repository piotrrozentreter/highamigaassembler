; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; cpu.s - ExecBase AttnFlags CPU detection for HAS projects
; =============================================================================

CPU_TYPE_68000 EQU 0
CPU_TYPE_68010 EQU 1
CPU_TYPE_68020 EQU 2
CPU_TYPE_68030 EQU 3
CPU_TYPE_68040 EQU 4
CPU_TYPE_68060 EQU 5

EXECBASE_PTR    EQU $0004
EB_ATTNFLAGS    EQU $0128

    SECTION cpu_code,CODE

    XDEF GetCPUType

; -----------------------------------------------------------------------------
; Function: GetCPUType
; Input: none
; Output: d0=CPU_TYPE_* constant for the highest recognized processor feature
; Description: Classifies the CPU using ExecBase AttnFlags.
; Notes: Preserves a0 and uses only Motorola 68000-compatible instructions.
; -----------------------------------------------------------------------------
GetCPUType:
    move.l a0,-(sp)
    move.l EXECBASE_PTR.w,a0
    move.w EB_ATTNFLAGS(a0),d0

    btst #7,d0
    bne.s .cpu_68060
    btst #3,d0
    bne.s .cpu_68040
    btst #2,d0
    bne.s .cpu_68030
    btst #1,d0
    bne.s .cpu_68020
    btst #0,d0
    bne.s .cpu_68010

    moveq #CPU_TYPE_68000,d0
    bra.s .done

.cpu_68010:
    moveq #CPU_TYPE_68010,d0
    bra.s .done

.cpu_68020:
    moveq #CPU_TYPE_68020,d0
    bra.s .done

.cpu_68030:
    moveq #CPU_TYPE_68030,d0
    bra.s .done

.cpu_68040:
    moveq #CPU_TYPE_68040,d0
    bra.s .done

.cpu_68060:
    moveq #CPU_TYPE_68060,d0

.done:
    move.l (sp)+,a0
    rts