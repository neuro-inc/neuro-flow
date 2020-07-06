import click


@click.group()
def main() -> None:
    pass


@main.command()
def ps() -> None:
    pass


@main.command()
def run() -> None:
    pass


@main.command()
def logs() -> None:
    pass


@main.command()
def kill() -> None:
    pass
