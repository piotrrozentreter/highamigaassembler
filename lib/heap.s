; =============================================================================
; (c) 2026 by Piotr Rozentreter (Rozsoft)
; heap.s
; Memory block header format (8 bytes):
; +0.l: Block memory length in words
; +4.l: Block status (0=free, 1=occupied)
; End of heap is detected when length = 0

; =============================================================================

    XDEF HeapAlloc
    XDEF HeapInit
    XDEF HeapFree

; =============================================================================
; Public API
; =============================================================================

HEAP_BLOCK_FREE         EQU 0
HEAP_BLOCK_OCCUPIED     EQU 1
HEAP_HEADER_BYTES       EQU 8
HEAP_HEADER_WORDS       EQU 4
    ifnd HEAP_MEMORY
HEAP_MEMORY             EQU 10*1024       ; default heap size in bytes
    endif
    ifle HEAP_MEMORY-(HEAP_HEADER_BYTES*2+2)
    fail "HEAP_MEMORY too small"
    endc
NULL                    EQU 0

    ; Blitter-visible scratch/background buffers are allocated from this heap
    ; (via bob.s), so keep it in CHIP RAM on machines with FAST RAM.
    SECTION heap_data,bss_c
    even

heap_start:
    ds.b HEAP_MEMORY
heap_end:

    SECTION heap,code

HeapInit:
    movem.l a0-a1/d0,-(a7)
    lea heap_start,a0
    move.l #((HEAP_MEMORY-(HEAP_HEADER_BYTES*2))/2),d0
    move.l d0,(a0)                      ; initial free block length in words
    move.l #HEAP_BLOCK_FREE,4(a0)
    lea heap_end-HEAP_HEADER_BYTES,a1
    clr.l (a1)                          ; end marker length=0
    clr.l 4(a1)
    movem.l (a7)+,a0-a1/d0
    rts

; IN: Stack[8(a6)] - number of words to allocate
; OUT: D0 - address of allocated memory or NULL if no memory available
HeapAlloc:
    link a6,#0                      ; establish stack frame
    movem.l d1-d4/a0-a1,-(sp)       ; save registers
    
    move.l 8(a6),d0                 ; requested size in words

    ; validate request
    tst.l d0
    ble .no_memory_available        ; must be > 0
    cmp.l #((HEAP_MEMORY-8)/2),d0
    bgt .no_memory_available        ; larger than usable heap

    lea heap_start,a0               ; cursor at heap start

.scan_loop:
    move.l (a0),d2                  ; d2 = length (words)

    tst.l d2
    beq .alloc_at_end               ; end marker reached

    move.l 4(a0),d3                 ; d3 = status
    cmp.l #HEAP_BLOCK_OCCUPIED,d3
    beq .next_block                 ; skip occupied

    ; free block and big enough? (unsigned compare)
    cmp.l d0,d2
    blo .next_block

    ; remaining after taking request
    move.l d2,d4                    ; d4 = block length (unsigned)
    sub.l d0,d4                     ; d4 = remaining words

    ; if not enough room for a new header + at least 0 data, consume whole block
    cmp.l #HEAP_HEADER_WORDS,d4
    ble .alloc_whole

    subq.l #HEAP_HEADER_WORDS,d4    ; remove header cost for remainder

    ; split block
    move.l d0,(a0)                  ; write allocated header
    move.l #HEAP_BLOCK_OCCUPIED,4(a0)

    ; tail header location
    move.l a0,a1
    move.l d0,d3
    lsl.l #1,d3                     ; bytes of payload
    add.l d3,a1
    addq.l #HEAP_HEADER_BYTES,a1    ; skip allocated header

    move.l d4,(a1)                  ; write free tail header
    move.l #HEAP_BLOCK_FREE,4(a1)

    addq.l #HEAP_HEADER_BYTES,a0
    move.l a0,d0
    movem.l (sp)+,d1-d4/a0-a1
    unlk a6
    rts

.alloc_whole:
    move.l #HEAP_BLOCK_OCCUPIED,4(a0)
    addq.l #HEAP_HEADER_BYTES,a0
    move.l a0,d0
    movem.l (sp)+,d1-d4/a0-a1
    unlk a6
    rts

.next_block:
    move.l d2,d4                    ; use unsigned length in long
    lsl.l #1,d4                     ; bytes of payload
    addq.l #HEAP_HEADER_BYTES,d4    ; header size
    add.l d4,a0                     ; advance
    bra .scan_loop

.alloc_at_end:
    lea heap_end,a1
    sub.l a0,a1                     ; bytes left (from end marker position)
    move.l d0,d2
    lsl.l #1,d2                     ; bytes requested
    add.l #(HEAP_HEADER_BYTES*2),d2 ; header + new end marker
    cmp.l d2,a1
    blt .no_memory_available

    move.l d0,(a0)                  ; write header at end marker spot
    move.l #HEAP_BLOCK_OCCUPIED,4(a0)

    move.l d0,d2
    lsl.l #1,d2
    move.l a0,d3                    ; save header addr
    add.l d2,a0                     ; skip data
    addq.l #HEAP_HEADER_BYTES,a0    ; reach new end marker slot
    clr.l (a0)                      ; new end marker length=0
    clr.l 4(a0)

    move.l d3,d0
    addq.l #HEAP_HEADER_BYTES,d0
    movem.l (sp)+,d1-d4/a0-a1
    unlk a6
    rts

.no_memory_available:
    moveq #NULL,d0                  ; return NULL
    movem.l (sp)+,d1-d4/a0-a1       ; restore registers
    unlk a6
    rts

; IN: Stack[8(a6)] - pointer returned by HeapAlloc (address of data)
; Free the block and coalesce with adjacent free blocks where possible.
HeapFree:
    link a6,#0                      ; establish stack frame
    movem.l a0-a6/d1-d6,-(sp)       ; save address regs + data temps
    
    move.l 8(a6),d0                 ; load pointer parameter from stack
    tst.l d0
    beq .hf_done                    ; NULL -> nothing to do

    move.l d0,a0                    ; copy data pointer to A0 for addressing
    
    ; validate pointer is within heap bounds (header must be at data-4)
    lea heap_start,a2
    lea heap_end,a3
    move.l a0,a4                    ; temp address for bounds check
    subq.l #HEAP_HEADER_BYTES,a4    ; a4 = header address
    cmp.l a2,a4
    blo .hf_done                    ; header before heap start (unsigned compare)
    cmp.l a3,a4
    bcc .hf_done                    ; header at or beyond heap end (unsigned compare)
    
    move.l a4,a0                    ; a0 = header address (already calculated above)
    move.l 4(a0),d2                 ; status
    cmp.l #HEAP_BLOCK_OCCUPIED,d2
    bne .hf_done                    ; already free or invalid

    ; mark as free
    move.l #HEAP_BLOCK_FREE,4(a0)

    ; try to coalesce with next blocks
.hf_coalesce_next:
    move.l (a0),d3                  ; cur_words
    move.l d3,d4
    lsl.l #1,d4                     ; bytes for data
    add.l #HEAP_HEADER_BYTES,d4     ; include header
    move.l a0,a1                    ; copy header addr to A1
    add.l d4,a1                     ; a1 = next header address
    cmp.l a3,a1
    bcc .hf_after_forward
    move.l (a1),d6                  ; next length
    tst.l d6
    beq .hf_after_forward           ; next is end marker (length=0)
    move.l 4(a1),d2                 ; next status
    cmp.l #HEAP_BLOCK_FREE,d2
    bne .hf_after_forward           ; next not free
    ; next is free and has non-zero length -> merge
    move.l d3,d4                    ; cur_words -> use D4 as temp (preserve D0 for backward scan)
    add.l d6,d4
    add.l #HEAP_HEADER_WORDS,d4     ; account for removed header
    move.l d4,(a0)                  ; write merged length at current header
    move.l #HEAP_BLOCK_FREE,4(a0)
    bra .hf_coalesce_next           ; try to merge further

.hf_after_forward:
    ; try to coalesce backward: find previous block by scanning from heap_start
    lea heap_start,a2
    move.l a2,a3                    ; cursor
.hf_find_prev:
    move.l (a3),d3                  ; words
    move.l d3,d4
    lsl.l #1,d4
    add.l #HEAP_HEADER_BYTES,d4
    move.l a3,a5
    add.l d4,a5                     ; a5 = next header after cursor
    cmp.l a5,a0
    beq .hf_prev_check
    lea heap_end,a4
    cmp.l a4,a5
    bcc .hf_done                    ; if a5 >= heap_end, stop searching
    move.l a5,a3
    bra.s .hf_find_prev

.hf_prev_check:
    ; a3 is prev header, check if free
    move.l 4(a3),d2
    cmp.l #HEAP_BLOCK_FREE,d2
    bne .hf_done                    ; prev not free
    ; merge prev and current: new_words = prev_words + cur_words + 2
    move.l (a3),d3                  ; prev_words
    move.l (a0),d6                  ; cur_words
    add.l d3,d6
    add.l #HEAP_HEADER_WORDS,d6
    move.l d6,(a3)                  ; write merged length at prev header
    move.l #HEAP_BLOCK_FREE,4(a3)
    bra .hf_done

.hf_done:
    movem.l (sp)+,d1-d6/a0-a6
    unlk a6
    rts
