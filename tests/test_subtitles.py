from app.services.subtitles import cue_ranges, format_ass_time, write_ass


def test_cues_follow_speech_not_padding():
    assert cue_ranges([(5.0, 2.0), (5.0, 4.0)]) == [(0.0, 2.0), (5.0, 9.0)]


def test_ass_time_and_cyrillic_file(tmp_path):
    assert format_ass_time(5.2) == "0:00:05.20"
    assert format_ass_time(3661.25) == "1:01:01.25"
    path = tmp_path / "subs.ass"
    write_ass(path, width=1920, height=1080, cues=[(0, 2.5, "Утро на набережной")])
    text = path.read_text(encoding="utf-8")
    assert "Утро на набережной" in text
    assert "PlayResX: 1920" in text
    assert "0:00:02.50" in text
