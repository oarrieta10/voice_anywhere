from voice_anywhere import pill
from voice_anywhere.pill import (BAR_MAX, BAR_WIDTH, HIDDEN, LISTENING, THINKING, PillAnimator,
                                 bar_heights, canvas_size, dot_brightness, render)


def test_silence_gives_round_dots_and_loud_gives_tall_bars():
    assert all(h == BAR_WIDTH for h in bar_heights(0.0, 1.0))
    loud = bar_heights(1.0, 1.0)
    assert max(loud) > 0.8 * BAR_MAX
    assert all(h <= BAR_MAX for h in loud)


def test_middle_bars_are_taller_than_the_ends_on_average():
    totals = [0.0] * pill.N_BARS
    for step in range(50):
        for i, h in enumerate(bar_heights(0.7, step * 0.07)):
            totals[i] += h
    assert totals[pill.N_BARS // 2] > totals[0] and totals[pill.N_BARS // 2] > totals[-1]


def test_louder_means_taller():
    assert sum(bar_heights(0.8, 2.0)) > sum(bar_heights(0.3, 2.0))


def test_dot_wave_moves():
    first, later = dot_brightness(0.0), dot_brightness(0.4)
    assert first.index(max(first)) != later.index(max(later))
    assert all(0.0 <= b <= 1.0 for b in first)


def test_render_size_follows_display_scaling():
    assert render(0.5, 0).size == canvas_size(1.0)
    assert render(0.5, 0, scale=1.5).size == canvas_size(1.5)


def test_render_is_transparent_around_the_pill_and_dark_inside():
    img = render(0.0, 0, appear=1.0)
    w, h = img.size
    assert img.getpixel((0, 0))[3] == 0  # corner outside the rounded pill
    r, g, b, a = img.getpixel((w // 4, 8))
    assert a > 200 and r < 40


def test_invisible_frame_is_fully_transparent():
    img = render(0.5, 0, appear=0.0)
    assert img.getchannel("A").getextrema() == (0, 0)


def test_thinking_pill_is_smaller():
    def width(img):
        box = img.getchannel("A").getbbox()
        return box[2] - box[0]

    assert width(render(0, 0, morph=1.0)) < width(render(0, 0, morph=0.0))


def test_message_draws_text_inside_the_pill():
    plain, message = render(0, 0), render(0, 0, text="Press your shortcut…")
    assert plain.size == message.size
    box = message.convert("L").point(lambda v: 255 if v > 200 else 0).getbbox()
    assert box[0] > 8 and box[2] < message.size[0] - 8  # the words fit, with room at the ends


def test_prompt_shows_and_hides_like_the_pill():
    a = PillAnimator()
    a.prompt("Press your shortcut…")
    run(a, 0.0, 0.5)
    assert a.state == pill.PROMPT and a.appear == 1.0
    a.hide()
    for step in range(10):
        last = a.frame(1.0 + 0.05 * step)
    assert last is None and not a.active
    a.listen()
    assert a.text is None


def run(animator, start, end, fps=30):
    """Ask for frames like the overlay window does; returns the last one."""
    frame, steps = None, round((end - start) * fps)
    for n in range(1, steps + 1):
        frame = animator.frame(start + n / fps)
    return frame


def test_animator_fades_in_morphs_and_fades_out():
    a = PillAnimator()
    assert a.frame(0.0) is None  # nothing to show yet
    a.listen()
    assert a.frame(0.0) is not None
    run(a, 0.0, 0.5)
    assert a.state == LISTENING and a.appear == 1.0
    a.set_level(1.0)
    a.frame(0.55)
    assert a.level > 0.5  # bars rise quickly
    a.think()
    a.frame(0.6)
    a.frame(0.7)
    a.frame(0.8)
    a.frame(0.9)
    assert a.state == THINKING and a.morph == 1.0
    assert a.level < 0.1  # bars fall when no longer listening
    a.hide()
    for step in range(10):
        last = a.frame(1.0 + 0.05 * step)
    assert last is None and a.state == HIDDEN and not a.active


def test_listening_again_after_hiding_starts_with_bars():
    a = PillAnimator()
    a.listen()
    a.frame(0)
    a.think()
    a.frame(0.05)
    a.frame(0.15)
    a.frame(0.5)
    a.hide()
    for step in range(10):
        a.frame(1 + 0.05 * step)
    a.listen()
    a.frame(2.0)
    assert a.morph == 0.0
