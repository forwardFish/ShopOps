from __future__ import annotations

import sys
import textwrap

from data_robot.full_flow import OPENPYXL_DEFAULT_STYLE_WARNING_FILTER, child_python_warnings, run_command


def test_child_python_warnings_adds_openpyxl_filter_without_overwriting_existing():
    value = child_python_warnings("default")

    assert value == f"default,{OPENPYXL_DEFAULT_STYLE_WARNING_FILTER}"
    assert child_python_warnings(value) == value


def test_run_command_suppresses_openpyxl_default_style_warning(tmp_path):
    script = tmp_path / "emit_openpyxl_warning.py"
    script.write_text(
        textwrap.dedent(
            """
            import warnings

            warnings.warn("Workbook contains no default style, apply openpyxl's default", UserWarning)
            print("ok")
            """
        ).strip(),
        encoding="utf-8",
    )

    result = run_command([sys.executable, str(script)], timeout=30)

    assert result["returncode"] == 0
    assert result["stdout_tail"].strip() == "ok"
    assert result["stderr_tail"] == ""
