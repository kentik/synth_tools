from pathlib import Path
from typing import List, Optional

import typer

from kentik_synth_client import KentikAPIRequestError, KentikSynthClient, TestStatus
from kentik_synth_client.synth_tests import SynTest
from synth_tools.core import load_test, make_test_results, run_one_shot
from synth_tools.matchers import all_matcher_from_rules
from synth_tools.utils import (
    dump_test_results,
    fail,
    get_api,
    print_dict,
    print_test,
    print_test_brief,
    print_test_results,
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
    wait_factor: float = typer.Option(1.0, help="Multiplier for test period for computing wait time for test results"),
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
    test = load_test(api, test_config, fail)
    if not test:
        return  # not reached, load test does no return without valid test, but we need to make linters happy
    if print_config:
        print_test(test, show_all=show_all)

    tid, polls, health = run_one_shot(api, test, wait_factor=wait_factor, retries=retries, delete=delete)

    results = make_test_results(health, test_id=tid, polls=polls)
    dump_test_results(None, results, json_out=json_out)

    if summary:
        print_dict(
            dict(
                test_id=tid,
                type=test.type.value,
                name=test.name,
                agents=test.settings.agentIds,
                success=results["success"],
                polls=results["polls"],
            )
        )
    else:
        print_test_results(results)

    if not results["success"]:
        fail(f"Test did not produce any health data in {results['polls']} retries")


@tests_app.command("create")
def create_test(
    ctx: typer.Context,
    test_config: Path = typer.Argument(..., help="Path to test config file"),
    dry_run: bool = typer.Option(False, help="Only construct and print test data"),
    print_config: bool = typer.Option(False, help="Print test configuration"),
    fields: Optional[str] = typer.Option(None, "-f", "--fields", help="Config attributes to print"),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
) -> None:
    """
    Create test
    """
    api = get_api(ctx)
    test = load_test(api, test_config, fail)
    if not test:
        return  # not reached, load test does no return without valid test, but we need to make linters happy
    if dry_run:
        print_test(test, show_all=show_all, attributes=fields)
        if not test:
            return  # not reached, load test does no return without valid test, but we need to make linters happy
    else:
        test = api.syn.create_test(test)
        if not test:
            return  # not reached, load test does no return without valid test, but we need to make linters happy
        typer.echo(f"Created new test: id {test.id}")
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
    for t in api.syn.tests:
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
    for i in test_ids:
        t = _get_test_by_id(api.syn, i)
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
    health = api.syn.results(t, periods=periods)

    if not health:
        fail(f"Test '{test_id}' did not produce any health data")

    results = make_test_results(health[0])
    dump_test_results(health, results, raw_out=raw_out, json_out=json_out)
    print_test_results(results)
