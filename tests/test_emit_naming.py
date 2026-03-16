from market_signal_system.utils.emit_naming import (
    build_emit_filename,
    normalize_emit_segment,
    normalize_emit_separator,
    validate_emit_template,
)


def test_build_emit_filename_supports_prefix_and_tag() -> None:
    assert (
        build_emit_filename(
            symbol="qqq",
            separator="-",
            prefix="nightly",
            tag="r2",
        )
        == "nightly-score-vs-macd-qqq-{ts}-r2.json"
    )


def test_build_emit_filename_supports_template() -> None:
    assert (
        build_emit_filename(
            symbol="eth",
            template="demo_{symbol}_{ts}",
        )
        == "demo_eth_{ts}.json"
    )


def test_validate_emit_template_requires_placeholders() -> None:
    try:
        validate_emit_template("demo_{symbol}")
        assert False, "should raise"
    except ValueError as exc:
        assert "{ts}" in str(exc)


def test_normalize_emit_segment_and_separator_reject_path_separator() -> None:
    try:
        normalize_emit_segment("bad/name", "--emit-prefix")
        assert False, "should raise"
    except ValueError as exc:
        assert "路径分隔符" in str(exc)

    try:
        normalize_emit_separator(" / ", "--emit-separator")
        assert False, "should raise"
    except ValueError as exc:
        assert "路径分隔符" in str(exc)
