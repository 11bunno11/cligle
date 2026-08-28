"""Allow the project directory to be run with ``python3 .``."""

if __package__:
    from .cligle import main
else:
    from cligle import main


if __name__ == "__main__":
    raise SystemExit(main())
