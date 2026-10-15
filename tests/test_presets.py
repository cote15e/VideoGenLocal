from app.presets import PRESETS, cover_filter, cover_scale


def test_platform_frame_sizes():
    sizes = {preset.key: (preset.width, preset.height) for preset in PRESETS}
    assert sizes == {
        "youtube": (1920, 1080),
        "shorts": (1080, 1920),
        "feed": (1080, 1080),
    }


def test_cover_filter_scales_uniformly_then_crops():
    video_filter = cover_filter(1920, 1080)
    assert "force_original_aspect_ratio=increase" in video_filter
    assert "scale=1920:1080" in video_filter
    assert "crop=1920:1080" in video_filter


def test_cover_scale_does_not_stretch():
    src_w, src_h = 1920, 1080
    scaled_w, scaled_h = cover_scale(src_w, src_h, 1080, 1920)
    assert abs((scaled_w / scaled_h) - (src_w / src_h)) < 1e-6
    assert scaled_w + 1e-6 >= 1080
    assert scaled_h + 1e-6 >= 1920


def test_square_master_covers_every_preset():
    for preset in PRESETS:
        scaled_w, scaled_h = cover_scale(1920, 1920, preset.width, preset.height)
        assert scaled_w + 1e-6 >= preset.width
        assert scaled_h + 1e-6 >= preset.height
        assert abs((scaled_w / scaled_h) - 1) < 1e-6
