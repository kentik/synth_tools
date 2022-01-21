from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import typer

from kentik_synth_client import KentikAPIRequestError, KentikSynthClient
from kentik_synth_client.synth_tests import SynTest
from kentik_synth_client.types import TestStatus
from synth_tools import log
from synth_tools.core import TestResults, load_test, run_one_shot
from synth_tools.matchers import all_matcher_from_rules
from synth_tools.utils import (
    api_request,
    dict_to_json,
    fail,
    get_api,
    print_struct,
    print_test,
    print_test_diff,
    print_test_results,
    print_tests_brief,
    sort_id,
    test_to_dict,
)

tests_app = typer.Typer()


def _get_test_by_id(api: KentikSynthClient, test_id: str) -> SynTest:
    try:
        return api.test(test_id)
    except KentikAPIRequestError as exc:
        if exc.response.status_code == 404:
            fail(f"Test with id '{test_id}' does not exist")
        else:
            fail(f"{exc}")
    return SynTest(name="non-existent")  # never reached, because fail function (or other exception) terminates the app


def _parse_substitution(substitutions: Optional[str]) -> Optional[Dict[str, str]]:
    subs: Optional[Dict[str, str]] = None
    if substitutions:
        subs = dict()
        for e in substitutions.split(","):
            f = e.split(":")
            if len(f) != 2:
                fail(f"Invalid substitution item '{e}' in substitutions ('{substitutions}')")
            subs[f"@{f[0]}@"] = f[1]
    return subs


def _parse_timestamp(ts: str) -> datetime:
    try:
        t = datetime.fromisoformat(ts)
        if not t.tzname():
            return datetime.fromisoformat(t.isoformat()+"+00:00")
        else:
            return t
    except ValueError as exc:
        fail(f"Failed to parse timestamp: {exc}")


@tests_app.command()
def one_shot(
    ctx: typer.Context,
    test_config: Path = typer.Argument(..., help="Path to test config file"),
    retries: int = typer.Option(3, help="Number retries waiting for test results"),
    summary: bool = typer.Option(False, help="Print summary rest results"),
    delete: bool = typer.Option(True, help="Delete test after retrieving results"),
    print_config: bool = typer.Option(False, help="Print test configuration"),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
    json_out: Optional[str] = typer.Option(None, help="Path to store test results in JSON format"),
    substitutions: Optional[str] = typer.Option(
        None, "-s", "--substitute", help="Comma separated list of substitutions in the form of 'var:value'"
    ),
) -> None:
    """
    Create test, wait until it produces results and delete or disable it
    """
    api = get_api(ctx)
    test = load_test(api, test_config, _parse_substitution(substitutions), fail=fail)
    if not test:
        return  # not reached, load test does no return without valid test, but we need to make linters happy
    if print_config:
        print_test(test, show_all=show_all)

    typer.echo("Waiting for test to accumulate results ...")
    results = run_one_shot(api, test, retries=retries, delete=delete)

    if json_out:
        log.info("Writing results to %s", json_out)
        dict_to_json(json_out, results.to_dict())

    if summary:
        print_struct(
            dict(
                id=results.test_id,
                type=results.test_type,
                name=results.test_name,
                status=results.status.name,
                agents=results.test_agents,
                polls=results.polls,
            )
        )
    else:
        print_struct(results.to_dict())


@tests_app.command("create")
def create_test(
    ctx: typer.Context,
    test_config: Path = typer.Argument(..., help="Path to test config file"),
    dry_run: bool = typer.Option(False, help="Only construct and print test data"),
    print_config: bool = typer.Option(False, help="Print test configuration"),
    fields: Optional[str] = typer.Option(None, "-f", "--fields", help="Config attributes to print"),
    substitutions: Optional[str] = typer.Option(
        None, "-s", "--substitute", help="Comma separated list of substitutions in the form of 'var:value'"
    ),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
) -> None:
    """
    Create test
    """
    api = get_api(ctx)
    test = load_test(api, test_config, _parse_substitution(substitutions), fail)
    if not test:
        return  # not reached, load test does no return without valid test, but we need to make linters happy
    if dry_run:
        print_test(test, show_all=show_all, attributes=fields)
    else:
        test = api_request(api.syn.create_test, "TestCreate", test)
        if not test:
            return  # to make linters happy - api_request does not return on failure
        typer.echo(f"Created new test: id {test.id}")
        if print_config:
            print_test(test, show_all=show_all)


#  UNFORTUNATELY CANNOT BE QUITE SUPPORTED YET
# @tests_app.command("update")
# def update_test(
#     ctx: typer.Context,
#     test_id: str = typer.Argument(..., help="Id of the test to update"),
#     test_config: Path = typer.Argument(..., help="Path to test config file"),
#     dry_run: bool = typer.Option(False, help="Construct new test config and compare it to existing"),
#     print_config: bool = typer.Option(False, help="Print test configuration"),
#     substitutions: Optional[str] = typer.Option(
#         None, "-s", "--substitute", help="Comma separated list of substitutions in the form of 'var:value'"
#     ),
#     show_all: bool = typer.Option(False, help="Show all test attributes"),
# ) -> None:
#     """
#     Update existing test
#     """
#     api = get_api(ctx)
#     old = _get_test_by_id(api.syn, test_id)
#     subs: Optional[dict] = None
#     new = load_test(api, test_config, _parse_substitutions(substitutions), fail)
#     if not new:
#         return  # not reached, load test does no return without valid test, but we need to make linters happy
#     if dry_run:
#         print_test_diff(old, new, labels=("EXISTING", "NEW"), show_all=show_all)
#     else:
#         new.status = old.status
#         test = api_request(api.syn.patch_test, "TestPatch", new, old.id, make_mod_mask(old, new))
#         typer.echo(f"Updated test: id {test.id}")
#         if print_config:
#             print_test(test, show_all=show_all)


@tests_app.command("compare_config")
def compare_test_config(
    ctx: typer.Context,
    test_id: str = typer.Argument(..., help="Id of the test to work on"),
    test_config: Path = typer.Argument(..., help="Path to test config file"),
    substitutions: Optional[str] = typer.Option(
        None, "-s", "--substitute", help="Comma separated list of substitutions in the form of 'var:value'"
    ),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
) -> None:
    """
    Construct test from config and compare to an existing test
    """
    api = get_api(ctx)
    old = _get_test_by_id(api.syn, test_id)
    new = load_test(api, test_config, _parse_substitution(substitutions), fail)
    if not new:
        return  # not reached, load test does no return without valid test, but we need to make linters happy
    print_test_diff(old, new, labels=(f"TEST: {old.id}", "Config file"), show_all=show_all)


@tests_app.command("delete")
def delete_test(ctx: typer.Context, test_ids: List[str] = typer.Argument(..., help="ID of the test to delete")) -> None:
    """
    Delete test
    """
    api = get_api(ctx)
    for i in test_ids:
        # Try to fetch test first in order to provide better error message if the test does not exist
        _get_test_by_id(api.syn, i)
        api_request(api.syn.delete_test, "TestDelete", i)
        typer.echo(f"Deleted test: id: {i}")


@tests_app.command("list")
def list_tests(
    ctx: typer.Context,
    brief: bool = typer.Option(False, "-b", "--brief", help="Print only id, name and type"),
    fields: Optional[str] = typer.Option(None, "-f", "--fields", help="Config attributes to print"),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
) -> None:
    """
    List all tests
    """
    api = get_api(ctx)
    tests = api_request(api.syn.list_tests, "ListTests")
    if brief:
        print_tests_brief(sorted(tests, key=lambda x: sort_id(x.id)))
    else:
        for t in sorted(tests, key=lambda x: sort_id(x.id)):
            if fields == "id":
                typer.echo(t.id)
            else:
                typer.echo(f"id: {t.id}")
                print_test(t, indent_level=1, show_all=show_all, attributes=fields)


@tests_app.command("get")
def get_test(
    ctx: typer.Context,
    test_ids: List[str],
    brief: bool = typer.Option(False, "-b", "--brief", help="Print only id, name and type"),
    fields: Optional[str] = typer.Option(None, "-f", "--fields", help="Config attributes to print"),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
) -> None:
    """
    Print test configuration
    """
    api = get_api(ctx)
    tests = [_get_test_by_id(api.syn, i) for i in test_ids]
    print_id = len(tests) > 1 and (not fields or "id" not in fields.split(","))
    if brief:
        print_tests_brief(tests)
    else:
        for t in tests:
            if print_id:
                typer.echo(f"id: {t.id}")
            print_test(t, show_all=show_all, attributes=fields)


@tests_app.command("match")
def match_test(
    ctx: typer.Context,
    rules: List[str],
    brief: bool = typer.Option(False, "-b", "--brief", help="Print only id, name and type"),
    fields: Optional[str] = typer.Option(None, "-f", "--fields", help="Config attributes to print"),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
) -> None:
    """
    Print configuration of test matching specified rules
    """
    api = get_api(ctx)
    matcher = all_matcher_from_rules(rules)
    tests = api_request(api.syn.list_tests, "ListTests")
    matching = [t for t in tests if matcher.match(test_to_dict(t))]
    if not matching:
        typer.echo("No test matches specified rules")
    else:
        matching.sort(key=lambda x: sort_id(x.id))
        if brief:
            print_tests_brief(matching)
        else:
            for t in matching:
                if fields == "id":
                    typer.echo(t.id)
                else:
                    typer.echo(f"id: {t.id}")
                    print_test(
                        t,
                        indent_level=1,
                        show_all=show_all,
                        attributes=fields,
                    )


@tests_app.command("compare")
def compare_test(
    ctx: typer.Context,
    test_id1: str = typer.Argument(..., help="Id of the first test to compare"),
    test_id2: str = typer.Argument(..., help="Id of the second test to compare"),
    print_config: bool = typer.Option(False, help="Print test configuration"),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
) -> None:
    """
    Compare configurations of 2 existing tests
    """
    api = get_api(ctx)
    t1 = _get_test_by_id(api.syn, test_id1)
    t2 = _get_test_by_id(api.syn, test_id2)
    print_test_diff(t1, t2, labels=(f"test {test_id1}", f"test {test_id2}"), show_all=show_all)
    if print_config:
        typer.echo(f"\ntest 1 ({test_id1}):")
        print_test(t1, indent_level=1, show_all=show_all)
        typer.echo(f"\ntest 2 ({test_id2}):")
        print_test(t2, indent_level=1, show_all=show_all)


@tests_app.command("pause")
def pause_test(ctx: typer.Context, test_id: str) -> None:
    """
    Pause test execution
    """
    api = get_api(ctx)
    # Try to fetch test first in order to provide better error message if the test does not exist
    _get_test_by_id(api.syn, test_id)
    api_request(api.syn.set_test_status, "TestStatusUpdate", test_id, TestStatus.paused)
    typer.echo(f"test id: {test_id} has been paused")


@tests_app.command("resume")
def resume_test(ctx: typer.Context, test_id: str) -> None:
    """
    Resume test execution
    """
    api = get_api(ctx)
    # Try to fetch test first in order to provide better error message if the test does not exist
    _get_test_by_id(api.syn, test_id)
    api_request(api.syn.set_test_status, "TestStatusUpdate", test_id, TestStatus.active)
    typer.echo(f"test id: {test_id} has been resumed")


@tests_app.command("results")
def get_test_health(
    ctx: typer.Context,
    test_id: str,
    raw_out: Optional[str] = typer.Option("", help="Path to file to store raw test results API response"),
    json_out: Optional[str] = typer.Option(None, help="Path to file to store test results in JSON format"),
    start: Optional[str] = typer.Option(
        None,
        "-f",
        "--from",
        help="Timestamp (in ISO format) of the earliest sample to return. UTC timezone is assumed if none is specified",
    ),
    end: Optional[str] = typer.Option(
        None,
        "-t",
        "--to",
        help="Timestamp (in ISO format) of the newest sample to return. UTC timezone is assumed if none is specified",
    ),
    periods: int = typer.Option(3, help="Number of test periods to the past to request (alternative to from/to)"),
) -> None:
    """
    Print test results and health status
    """
    if start:
        start_time = _parse_timestamp(start)
    else:
        start_time = None
    if end:
        end_time = _parse_timestamp(end)
    else:
        end_time = None
    api = get_api(ctx)
    t = _get_test_by_id(api.syn, test_id)
    health = api_request(api.syn.results, "GetHealthForTests", t, start=start_time, end=end_time, periods=periods)
    if not health:
        fail(f"Test '{test_id}' did not produce any health data")

    results = TestResults(t)
    results.set_health(health[0])
    if raw_out:
        log.info("Writing health data to %s", raw_out)
        dict_to_json(raw_out, health)
    if json_out:
        log.info("Writing results to %s", json_out)
        dict_to_json(json_out, results.to_dict())
    print_test_results(results.to_dict()["execution"]["results"])


@tests_app.command("trace")
def get_test_trace(
    ctx: typer.Context,
    test_id: str,
    targets: Optional[List[str]] = typer.Argument(None, help="Target IP addresses for which to retrieve trace data"),
    raw_out: Optional[str] = typer.Option("", help="Path to file to store raw API response in JSON format"),
    start: Optional[str] = typer.Option(
        None,
        "-f",
        "--from",
        help="Timestamp (in ISO format) of the earliest sample to return. UTC timezone is assumed if none is specified",
    ),
    end: Optional[str] = typer.Option(
        None,
        "-t",
        "--to",
        help="Timestamp (in ISO format) of the newest sample to return. UTC timezone is assumed if none is specified",
    ),
    periods: int = typer.Option(3, help="Number of test periods to request"),
) -> None:
    """
    Print test trace data
    """
    if start:
        start_time = _parse_timestamp(start)
    else:
        start_time = None
    if end:
        end_time = _parse_timestamp(end)
    else:
        end_time = None
    api = get_api(ctx)
    t = _get_test_by_id(api.syn, test_id)
    trace = api_request(
        api.syn.trace, "GetTraceForTests", t, start=start_time, end=end_time, periods=periods, ips=targets
    )
    if not trace:
        fail(f"Test '{test_id}' did not produce any trace data")
    if raw_out:
        log.info("Writing trace data to %s", raw_out)
        dict_to_json(raw_out, trace)
    print_struct(trace)
