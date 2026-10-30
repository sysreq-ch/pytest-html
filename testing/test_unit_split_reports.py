# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import html as html_module
import json
from pathlib import Path
import re

import pytest

from pytest_html import extras  # noqa: F401

pytest_plugins = ("pytester",)


def run(pytester, path="report.html", cmd_flags=None):
    cmd_flags = cmd_flags or []
    path = pytester.path.joinpath(path)
    return pytester.runpytest("--html", path, *cmd_flags)


def _parse_jsonblob(pytester, report_path):
    path = pytester.path / report_path
    with open(path, encoding="utf-8") as f:
        content = f.read()
    match = re.search(r'data-jsonblob=\"([^\"]+)\"', content)
    if not match:
        return None
    raw = match.group(1)
    decoded = html_module.unescape(raw)
    return json.loads(decoded)


def get_results_in_report(pytester, report_path):
    data = _parse_jsonblob(pytester, report_path)
    if not data:
        return []
    tests = data["tests"]
    results = []
    for nodeid, test_list in tests.items():
        for t in test_list:
            results.append(t.get("result", "N/A"))
    return results


def test_split_reports_cli_one_outcome(pytester):
    pytester.makepyfile(test_example="def test_pass(): pass\n")
    pytester.makepyfile(test_fail="def test_fail(): assert 0")

    result = run(pytester, "report.html", cmd_flags=["--split-reports=failed"])
    result.assert_outcomes(passed=1, failed=1)

    assert (pytester.path / "report.html").exists()
    assert (pytester.path / "report_failed.html").exists()


def test_split_reports_ini_multiple_outcomes(pytester):
    pytester.makeini("""
        [pytest]
        split_reports = passed,failed
    """)

    pytester.makepyfile(test_pass="def test_pass(): pass")
    pytester.makepyfile(test_fail="def test_fail(): assert 0")

    result = run(pytester, "report.html")
    result.assert_outcomes(passed=1, failed=1)

    assert (pytester.path / "report.html").exists()
    assert (pytester.path / "report_passed.html").exists()
    assert (pytester.path / "report_failed.html").exists()


def test_split_reports_all_outcomes(pytester):
    pytester.makepyfile(
        test_it="""
        import pytest
        def test_pass():
            pass
        def test_fail():
            assert 0
        def test_skip():
            pytest.skip('skipped')
        """
    )

    result = run(pytester, "report.html", cmd_flags=["--split-reports=all"])
    result.assert_outcomes(passed=1, failed=1, skipped=1)

    assert (pytester.path / "report.html").exists()
    assert (pytester.path / "report_passed.html").exists()
    assert (pytester.path / "report_failed.html").exists()
    assert (pytester.path / "report_skipped.html").exists()


def test_split_reports_invalid_outcome(pytester):
    pytester.makepyfile(test_example="def test_example(): pass")

    with pytest.warns(UserWarning, match="Unknown outcome 'invalid'"):
        result = run(pytester, "report.html", cmd_flags=["--split-reports=invalid,passed"])
    result.assert_outcomes(passed=1)

    # invalid outcome creates no split report; valid ones still work
    assert not Path(pytester.path, "report_invalid.html").exists()
    assert Path(pytester.path, "report_passed.html").exists()


def test_split_reports_bundled_group(pytester):
    pytester.makepyfile(
        test_it="""
        import pytest

        @pytest.fixture
        def broken():
            raise RuntimeError("boom")

        def test_fail():
            assert 0

        def test_error(broken):
            pass
        """
    )

    result = run(pytester, "report.html", cmd_flags=["--split-reports=failed+error"])
    result.assert_outcomes(failed=1, errors=1)

    bundle = get_results_in_report(pytester, "report_error_failed.html")
    assert sorted(bundle) == ["Error", "Failed"]
    # the bundled outcomes get no separate reports of their own
    assert not (pytester.path / "report_failed.html").exists()
    assert not (pytester.path / "report_error.html").exists()


def test_split_reports_group_order_normalized(pytester):
    pytester.makepyfile(
        test_it="""
        def test_pass():
            pass

        def test_fail():
            assert 0
        """
    )

    result = run(pytester, "report.html", cmd_flags=["--split-reports=error+failed"])
    result.assert_outcomes(passed=1, failed=1)

    # token order is normalized, so error+failed uses the same file as failed+error
    assert (pytester.path / "report_error_failed.html").exists()


def test_split_reports_no_split_outcome_matches(pytester):
    pytester.makepyfile(
        test_pass="def test_pass(): pass",
        test_fail="def test_fail(): assert 0"
    )

    result = run(pytester, "report.html", cmd_flags=["--split-reports=skipped"])
    result.assert_outcomes(passed=1, failed=1)

    assert not (pytester.path / "report_skipped.html").exists()


def test_split_reports_default_behavior_no_split(pytester):
    pytester.makepyfile(test_example="def test_example(): pass")

    result = run(pytester, "report.html")
    result.assert_outcomes(passed=1)

    assert (pytester.path / "report.html").exists()
    assert not (pytester.path / "report_passed.html").exists()


def test_split_reports_preserves_metadata(pytester):
    pytester.makeconftest("""
        import pytest
        from pytest_html import extras
        @pytest.hookimpl(hookwrapper=True)
        def pytest_runtest_makereport(item, call):
            outcome = yield
            report = outcome.get_result()
            if report.when == "call":
                report.extras = [extras.url("http://example.com")]
    """)

    pytester.makepyfile(test_fail="def test_fail(): assert 0")

    result = run(pytester, "report.html", cmd_flags=["--split-reports=failed"])
    result.assert_outcomes(failed=1)

    results = get_results_in_report(pytester, "report.html")
    assert len(results) == 1

    results = get_results_in_report(pytester, "report_failed.html")
    assert len(results) == 1


def test_split_reports_with_selfcontained_html(pytester):
    pytester.makepyfile(test_pass="def test_pass(): pass")
    pytester.makepyfile(test_fail="def test_fail(): assert 0")

    result = run(pytester, "report.html", cmd_flags=["--self-contained-html", "--split-reports=failed"])
    result.assert_outcomes(passed=1, failed=1)

    assert (pytester.path / "report.html").exists()
    assert (pytester.path / "report_failed.html").exists()

    results = get_results_in_report(pytester, "report_failed.html")
    assert len(results) == 1


def test_split_reports_outcome_counts(pytester):
    pytester.makepyfile(
        test_t1="def test_t1(): pass",
        test_t2="def test_t2(): pass",
        test_t3="def test_t3(): assert 0",
        test_t4="def test_t4(): assert 0"
    )

    result = run(pytester, "report.html", cmd_flags=["--split-reports=passed,failed"])
    result.assert_outcomes(passed=2, failed=2)

    results_all = get_results_in_report(pytester, "report.html")
    assert len(results_all) == 4

    results_passed = get_results_in_report(pytester, "report_passed.html")
    assert all(r == "Passed" for r in results_passed)
    assert len(results_passed) == 2

    results_failed = get_results_in_report(pytester, "report_failed.html")
    assert all(r == "Failed" for r in results_failed)
    assert len(results_failed) == 2


def test_split_reports_outcome_counts_isolated(pytester):
    pytester.makepyfile(
        test_t1="def test_t1(): pass",
        test_t2="def test_t2(): pass",
        test_t3="def test_t3(): assert 0",
    )

    result = run(pytester, "report.html", cmd_flags=["--split-reports=failed"])
    result.assert_outcomes(passed=2, failed=1)

    data = _parse_jsonblob(pytester, "report_failed.html")
    # Only the failed test should be in the filtered report
    tests = data["tests"]
    test_count = sum(len(v) for v in tests.values())
    assert test_count == 1
    for nodeid, test_list in tests.items():
        for t in test_list:
            assert t.get("result") == "Failed"


def test_split_reports_custom_html_path(pytester):
    report_dir = pytester.path / "reports"
    report_dir.mkdir()

    pytester.makepyfile(test_pass="def test_pass(): pass")
    pytester.makepyfile(test_fail="def test_fail(): assert 0")

    result = run(pytester, "reports/summary.html", cmd_flags=["--split-reports=failed"])
    result.assert_outcomes(passed=1, failed=1)

    assert (report_dir / "summary.html").exists()
    assert (report_dir / "summary_failed.html").exists()


def test_split_reports_with_generate_report_on_test(pytester):
    pytester.makeini("""
        [pytest]
        split_reports = failed
        generate_report_on_test = true
    """)

    pytester.makepyfile(
        test_t1="def test_t1(): pass",
        test_t2="def test_t2(): assert 0",
        test_t3="def test_t3(): assert 0"
    )

    result = run(pytester, "report.html")
    result.assert_outcomes(passed=1, failed=2)

    assert (pytester.path / "report.html").exists()
    assert (pytester.path / "report_failed.html").exists()

    results = get_results_in_report(pytester, "report_failed.html")
    assert len(results) == 2


def test_split_reports_rerun_outcome(pytester):
    pytester.makepyfile(
        test_it="""
        count = 0
        def test_rerun():
            global count
            count += 1
            assert count > 1
        """
    )

    result = run(pytester, "report.html", cmd_flags=["--split-reports=passed,rerun", "--reruns=1"])
    result.assert_outcomes(passed=1)

    assert (pytester.path / "report_rerun.html").exists()
    results = get_results_in_report(pytester, "report_rerun.html")
    assert len(results) == 1


def test_split_reports_terminal_summary(pytester):
    pytester.makepyfile(test_pass="def test_pass(): pass")

    result = run(pytester, "report.html", cmd_flags=["--split-reports=passed"])
    result.assert_outcomes(passed=1)

    result.stdout.fnmatch_lines([
        "*Generated html report: file://*report.html*",
        "*Generated html report (passed): file://*report_passed.html*",
    ])


def test_split_reports_outcome_case_normalized(pytester):
    pytester.makepyfile(test_pass="def test_pass(): pass")

    result = run(pytester, "report.html", cmd_flags=["--split-reports=Passed"])
    result.assert_outcomes(passed=1)

    # Should produce lowercase filename even with uppercase CLI arg
    assert (pytester.path / "report_passed.html").exists()


def test_split_reports_stale_file_removed(pytester):
    pytester.makepyfile(
        test_fail="def test_fail(): assert 0",
    )

    result = run(pytester, "report.html", cmd_flags=["--split-reports=failed"])
    result.assert_outcomes(failed=1)
    assert (pytester.path / "report_failed.html").exists()

    # Simulate stale file by writing one, then run with all-passing tests
    stale = pytester.path / "report_failed.html"
    stale.write_text("stale")
    (pytester.path / "test_fail.py").unlink()
    pytester.makepyfile(test_pass="def test_pass(): pass")

    result = run(pytester, "report.html", cmd_flags=["--split-reports=failed"])
    result.assert_outcomes(passed=1)
    assert not stale.exists()


def test_split_reports_xfail_xpass_outcomes(pytester):
    pytester.makepyfile(
        test_it="""
        import pytest
        @pytest.mark.xfail
        def test_xpassed():
            pass
        @pytest.mark.xfail
        def test_xfailed():
            assert 0
        """
    )

    result = run(pytester, "report.html", cmd_flags=["--split-reports=all"])
    result.assert_outcomes(xfailed=1, xpassed=1)

    assert (pytester.path / "report_xpassed.html").exists()
    assert (pytester.path / "report_xfailed.html").exists()

    results = get_results_in_report(pytester, "report_xpassed.html")
    assert all(r == "XPassed" for r in results)

    results = get_results_in_report(pytester, "report_xfailed.html")
    assert all(r == "XFailed" for r in results)
