from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
ANIMATION_ASM = ROOT / "lib" / "bob_animation.s"


def test_bob_animation_exports_complete_lifecycle() -> None:
    assembly = ANIMATION_ASM.read_text(encoding="utf-8")
    for symbol in (
        "CreateBobAnimation",
        "AddBobAnimationFrame",
        "PlayBobAnimation",
        "StopBobAnimation",
        "AnimateBob",
        "DestroyBobAnimation",
    ):
        assert re.search(rf"(?im)^\s*XDEF\s+{symbol}\s*$", assembly)
        assert re.search(rf"(?m)^{symbol}:\s*$", assembly)


def test_animation_tick_stops_or_wraps_at_the_last_frame() -> None:
    assembly = ANIMATION_ASM.read_text(encoding="utf-8")
    animate = assembly[assembly.index("AnimateBob:"):assembly.index("DestroyBobAnimation:")]

    assert "move.l FRAME_BOB(a1),d0" in animate
    assert "move.l FRAME_NEXT(a1),a2" in animate
    assert "move.w ANIM_FLAGS(a0),d1" in animate
    assert "btst #ANIM_PLAYING,d1" in animate
    assert "btst #ANIM_LOOPING,d1" in animate
    assert "move.l ANIM_HEAD(a0),a2" in animate
    assert "andi.w #$FFFE,ANIM_FLAGS(a0)" in animate
    assert "subq.w #1,ANIM_REMAINING(a0)\n    bne .ab_done" in animate


def test_delay_normalizer_has_module_scope_for_linking() -> None:
    assembly = ANIMATION_ASM.read_text(encoding="utf-8")
    assert assembly.count("bsr BobAnimationNormalizeDelay") == 2
    assert "\nBobAnimationNormalizeDelay:\n" in assembly


def test_build_scripts_resolve_animation_dependencies() -> None:
    for script_name in ("build_example.sh", "build_game.sh"):
        script = (ROOT / "scripts" / script_name).read_text(encoding="utf-8")
        assert '"$LIB_DIR/bob_animation.s"' in script
        assert "bob_animation.s)" in script
        assert '"$LIB_DIR/bob.s" "$LIB_DIR/heap.s"' in script