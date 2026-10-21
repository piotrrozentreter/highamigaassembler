---
name: has-ptplayer-audio
description: >-
  Wire ProTracker MOD music and IFF 8SVX sound effects into HAS Amiga games via
  ptplayer. Use when adding music, SFX, PlayMusic/PlaySoundEffect, MOD/IFF assets,
  extract_8svx, music_data.s/sounds_data.s, or linking the ptplayer library.
---

# HAS + ptplayer audio

Pattern used by **Graveyard Shadows** and **astronautjetpac**. Prefer this over inventing a custom Paula mixer.

## Pieces

| Piece | Role |
|---|---|
| `ptplayer` | HAS lib (`lib/ptplayer.s` + `ptplayer.i`); link in Makefile `LIBRARY_NAMES` |
| `assets/music_data.s` | `SECTION …,DATA_C`, `XDEF music`, `incbin` the `.mod` |
| `assets/sounds_data.s` | CHIP samples + `sfx_table` (`SfxStructure`-style: ptr, len words, period, vol, channel, pri) |
| `scripts/extract_8svx.py` | IFF 8SVX → raw PCM (`make sfx`) |
| HAS procs | `InitSound`, `PlayMusic`, `PlaySoundEffect(sfx_id)`, `QuitSound` |

## HAS API (minimal)

```has
native proc InitSound() -> void {
    asm {
        movem.l    d0/a0/a6,-(sp)
        lea        $DFF000,a6
        move.l     #0,a0          ; vectorBase
        moveq      #1,d0          ; PAL
        jsr        _mt_install_cia
        lea        $DFF000,a6
        move.b     #$01,d0        ; music owns channel 0
        jsr        _mt_musicmask
        movem.l    (sp)+,d0/a0/a6
    }
}

proc PlaySoundEffect(sfx_id: int) -> void {
    asm {
        movem.l    a6,-(sp)
        move.l     8(a6),d0
        clr.l      d1             ; no loop
        jsr        play_sfx
        movem.l    (sp)+,a6
    }
}

proc PlayMusic() -> void {
    asm {
        movem.l    a6,-(sp)
        lea        music,a0
        lea        $DFF000,a6
        move.l     #0,a1
        move.b     #0,d0
        jsr        _mt_init
        move.b     #1,_mt_Enable
        lea        $DFF000,a6
        move.w     #16,d0
        jsr        _mt_mastervol
        movem.l    (sp)+,a6
    }
}

native proc QuitSound() -> void {
    asm {
        movem.l    a6,-(sp)
        lea        $DFF000,a6
        jsr        _mt_end
        jsr        _mt_remove_cia
        movem.l    (sp)+,a6
    }
}
```

Lifecycle: call `InitSound` + `PlayMusic` after successful gfx/asset init; `QuitSound` before `ReleaseSystem`. Install CIA only when startup will continue (avoid orphan handlers on early failure).

## Makefile checklist

1. Add `ptplayer` to `LIBRARY_NAMES`.
2. `MUSIC_MOD` + rule: `music_data.o` depends on the `.mod`.
3. `SFX_NAMES` + `assets/sfx_%.raw: assets/%.iff` via `extract_8svx.py`.
4. `sounds_data.o` depends on all `SFX_RAW`.
5. Keep samples and MOD in **CHIP** (`DATA_C`).

Period for 8 kHz 8SVX: `≈ 3546895/8000 → 443`. Volume/priority per effect in `sfx_table`.

## SFX IDs

Define `const SFX_… = N` matching `sfx_table` order. Call `PlaySoundEffect(SFX_…)` at the gameplay event (spawn, hit, throw, death).

## References

- Working game: `graveyardshadowsamiga` (`graveyard.has`, `assets/music_data.s`, `assets/sounds_data.s`)
- Multi-track + `SwitchMusic`: `astronautjetpac/jetpac.has`
- Do not fight music channel 0; SFX use remaining Paula channels via `play_sfx`
