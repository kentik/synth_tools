import typer


def fail(msg: str) -> None:
    typer.echo(f"FAILED: {msg}", err=True)
    raise typer.Exit(1)
