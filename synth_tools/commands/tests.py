from pathlib import Path
from typing import List, Optional

import typer

from kentik_synth_client import TestStatus
from synth_tools.commands.utils import all_matcher_from_rules, fail, get_api, print_health, print_test, print_test_brief
from synth_tools.core import load_test, run_one_shot

tests_app = typer.Typer()


@tests_app.command()
def one_shot(
    ctx: typer.Context,
    test_config: Path = typer.Argument(..., help="Path to test config file"),
    wait_factor: float = typer.Option(1.0, help="Multiplier for test period for computing wait time for test results"),
    retries: int = typer.Option(3, help="Number retries waiting for test results"),
    raw_out: str = typer.Option("", help="Path to file to store raw test results in JSON format"),
    failing: bool = typer.Option(False, help="Print only failing results"),
    delete: bool = typer.Option(True, help="Delete test after retrieving results"),
    print_config: bool = typer.Option(False, help="Print test configuration"),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
    json_out: bool = typer.Option(False, "--json", help="Print output in JSON format"),
) -> None:
    """
    Create test, wait until it produces results and delete or disable it
    """
    api = get_api(ctx)
    test = load_test(api, test_config, fail)
    if print_config:
        print_test(test, show_all=show_all)
    health = run_one_shot(api, test, wait_factor=wait_factor, retries=retries, delete=delete)

    if not health:
        fail("Test did not produce any health data")
    else:
        print_health(health, raw_out=raw_out, failing_only=failing, json_out=json_out)


@tests_app.command("create")
def create_test(
    ctx: typer.Context,
    test_config: Path = typer.Argument(..., help="Path to test config file"),
    dry_run: bool = typer.Option(False, help="Only construct and print test data"),
    print_config: bool = typer.Option(False, help="Print test configuration"),
    attributes: Optional[str] = typer.Option(None, help="Config attributes to print"),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
) -> None:
    """
    Create test
    """
    api = get_api(ctx)
    test = load_test(api, test_config, fail)
    if dry_run:
        print_test(test, show_all=show_all, attributes=attributes)
    else:
        test = api.syn.create_test(test)
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
        api.syn.delete_test(i)
        typer.echo(f"Deleted test: id: {i}")


@tests_app.command("list")
def list_tests(
    ctx: typer.Context,
    brief: bool = typer.Option(False, help="Print only id, name and type"),
    attributes: Optional[str] = typer.Option(None, help="Config attributes to print"),
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
            typer.echo(f"id: {t.id}")
            print_test(t, indent_level=1, show_all=show_all, attributes=attributes)


@tests_app.command("get")
def get_test(
    ctx: typer.Context,
    test_ids: List[str],
    attributes: Optional[str] = typer.Option(None, help="Config attributes to print"),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
) -> None:
    """
    Print test configuration
    """
    api = get_api(ctx)
    for i in test_ids:
        t = api.syn.test(i)
        print_test(t, show_all=show_all, attributes=attributes)


@tests_app.command("match")
def match_test(
    ctx: typer.Context,
    rules: List[str],
    brief: bool = typer.Option(False, help="Print only id, name and type"),
    attributes: Optional[str] = typer.Option(None, help="Config attributes to print"),
    show_all: bool = typer.Option(False, help="Show all test attributes"),
) -> None:
    """
    Print configuration of test matching specified rules
    """
    api = get_api(ctx)
    matcher = all_matcher_from_rules(rules)
    matching = [t for t in api.syn.tests if matcher.match(t.to_dict()["test"])]
    if not matching:
        typer.echo("No test matches specified rules")
    else:
        for t in matching:
            if brief:
                print_test_brief(t)
            else:
                typer.echo(f"id: {t.id}")
                print_test(
                    t,
                    indent_level=1,
                    show_all=show_all,
                    attributes=attributes,
                )


@tests_app.command("pause")
def pause_test(ctx: typer.Context, test_id: str) -> None:
    """
    Pause test execution
    """
    api = get_api(ctx)
    api.syn.set_test_status(test_id, TestStatus.paused)
    typer.echo(f"test id: {test_id} has been paused")


@tests_app.command("resume")
def resume_test(ctx: typer.Context, test_id: str) -> None:
    """
    Resume test execution
    """
    api = get_api(ctx)
    api.syn.set_test_status(test_id, TestStatus.active)
    typer.echo(f"test id: {test_id} has been resumed")


@tests_app.command("results")
def get_test_health(
    ctx: typer.Context,
    test_id: str,
    raw_out: str = typer.Option("", help="Path to file to store raw test results in JSON format"),
    json_out: bool = typer.Option(False, "--json", help="Print output in JSON format"),
    failing: bool = typer.Option(False, help="Print only failing results"),
    periods: int = typer.Option(3, help="Number of test periods to request"),
) -> None:
    """
    Print test results and health status
    """
    api = get_api(ctx)
    t = api.syn.test(test_id)
    health = api.syn.results(t, periods=periods)

    if not health:
        fail(f"Test '{test_id}' did not produce any health data")

    print_health(health[0], raw_out=raw_out, failing_only=failing, json_out=json_out)
