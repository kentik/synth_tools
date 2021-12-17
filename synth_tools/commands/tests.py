from pathlib import Path
from typing import List, Optional

import typer

from kentik_synth_client import KentikAPIRequestError, KentikSynthClient
from kentik_synth_client.synth_tests import SynTest
from kentik_synth_client.types import TestStatus
from synth_tools import log
from synth_tools.core import TestResults, load_test, run_one_shot
from synth_tools.matchers import all_matcher_from_rules
from synth_tools.utils import (
    dict_to_json,
    fail,
    get_api,
    print_struct,
    print_test,
    print_test_brief,
    print_test_diff,
    print_test_results,
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
) -> None:
    """
    Create test, wait until it produces results and delete or disable it
    """
    api = get_api(ctx)
    test = load_test(api, test_config, fail=fail)
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
    subs: Optional[dict] = None
    if substitutions:
        subs = dict()
        for e in substitutions.split(","):
            f = e.split(":")
            if len(f) != 2:
                fail(f"Invalid substitution item '{e}' in substitutions ('{substitutions}')")
            subs[f"@{f[0]}@"] = f[1]
    test = load_test(api, test_config, subs, fail)
    if not test:
        return  # not reached, load test does no return without valid test, but we need to make linters happy
    if dry_run:
        print_test(test, show_all=show_all, attributes=fields)
    else:
        test = api.syn.create_test(test)
        if not test:
            return  # not reached, load test does no return without valid test, but we need to make linters happy
        typer.echo(f"Created new test: id {test.id}")
        if print_config:
            print_test(test, show_all=show_all)


@tests_app.command("update")
def update_test(
    ctx: typer.Context,
    test_id: str = typer.Argument(..., help="Id of the test to update"),
    test_config: Path = typer.Argument(..., help="Path to test config file"),
    dry_run: bool = typer.Option(False, help="Construct new test config and compare it to existing"),
    print_config: bool = typer.Option(False, help="Print test configuration"),
    substitutions: Optional[str] = typer.Option(
        None, "-s", "--substitute", help="Comma separated list of substitutions in the form of 'var:value'"
    ),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
) -> None:
    """
    Update existing test
    """
    api = get_api(ctx)
    old = _get_test_by_id(api.syn, test_id)
    subs: Optional[dict] = None
    if substitutions:
        subs = dict()
        for e in substitutions.split(","):
            f = e.split(":")
            if len(f) != 2:
                fail(f"Invalid substitution item '{e}' in substitutions ('{substitutions}')")
            subs[f"@{f[0]}@"] = f[1]
    new = load_test(api, test_config, subs, fail)
    if not new:
        return  # not reached, load test does no return without valid test, but we need to make linters happy
    if dry_run:
        print_test_diff(old, new, labels=("EXISTING", "NEW"), show_all=show_all)
    else:
        test = api.syn.update_test(new, old.id)
        if not test:
            return  # not reached, load test does no return without valid test, but we need to make linters happy
        typer.echo(f"Updated test: id {test.id}")
        if print_config:
            print_test(test, show_all=show_all)


@tests_app.command("delete")
def delete_test(ctx: typer.Context, test_ids: List[str] = typer.Argument(..., help="ID of the test to delete")) -> None:
    """
    Delete test
    """
    api = get_api(ctx)
    for i in test_ids:
        # Try to fetch test first in order to provide better error message if the test does not exist
        _get_test_by_id(api.syn, i)
        api.syn.delete_test(i)
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
    for t in sorted(api.syn.tests, key=lambda x: sort_id(x.id)):
        if brief:
            print_test_brief(t)
        else:
            if fields == "id":
                typer.echo(t.id)
            else:
                typer.echo(f"id: {t.id}")
                print_test(t, indent_level=1, show_all=show_all, attributes=fields)


@tests_app.command("get")
def get_test(
    ctx: typer.Context,
    test_ids: List[str],
    fields: Optional[str] = typer.Option(None, "-f", "--fields", help="Config attributes to print"),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
) -> None:
    """
    Print test configuration
    """
    api = get_api(ctx)
    print_id = len(test_ids) > 1 and (not fields or "id" not in fields.split(","))
    for i in test_ids:
        t = _get_test_by_id(api.syn, i)
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
    matching = [t for t in api.syn.tests if matcher.match(test_to_dict(t))]
    if not matching:
        typer.echo("No test matches specified rules")
    else:
        matching.sort(key=lambda x: sort_id(x.id))
        for t in matching:
            if brief:
                print_test_brief(t)
            else:
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
        typer.echo(f"\ntests 1 ({test_id1}):")
        print_test(t1, indent_level=1, show_all=show_all)
        typer.echo(f"\ntests 2 ({test_id2}):")
        print_test(t2, indent_level=1, show_all=show_all)


@tests_app.command("pause")
def pause_test(ctx: typer.Context, test_id: str) -> None:
    """
    Pause test execution
    """
    api = get_api(ctx)
    # Try to fetch test first in order to provide better error message if the test does not exist
    _get_test_by_id(api.syn, test_id)
    api.syn.set_test_status(test_id, TestStatus.paused)
    typer.echo(f"test id: {test_id} has been paused")


@tests_app.command("resume")
def resume_test(ctx: typer.Context, test_id: str) -> None:
    """
    Resume test execution
    """
    api = get_api(ctx)
    # Try to fetch test first in order to provide better error message if the test does not exist
    _get_test_by_id(api.syn, test_id)
    api.syn.set_test_status(test_id, TestStatus.active)
    typer.echo(f"test id: {test_id} has been resumed")


@tests_app.command("results")
def get_test_health(
    ctx: typer.Context,
    test_id: str,
    raw_out: Optional[str] = typer.Option("", help="Path to file to store raw test results API response"),
    json_out: Optional[str] = typer.Option(None, help="Path to file to store test results in JSON format"),
    periods: int = typer.Option(3, help="Number of test periods to request"),
) -> None:
    """
    Print test results and health status
    """
    api = get_api(ctx)
    t = _get_test_by_id(api.syn, test_id)
    try:
        health = api.syn.results(t, periods=periods)
    except Exception as exc:
        fail(f"Failed to get results ({exc}")
        health = None  # to make linters happy (this line is never reached)

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
