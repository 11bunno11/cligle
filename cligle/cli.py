#!/usr/bin/env python3
"""Command-line client for the search API."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen


DEFAULT_ENDPOINT = "https://serpapi.com/search.json"
DEFAULT_ENGINE = "google"
RESULTS_PER_PAGE = 10
DEFAULT_TIMEOUT = 30
DEFAULT_KEY_FILE = Path.home() / ".cligle" / "api_key.txt"
LEGACY_KEY_FILE = Path(__file__).resolve().parent / "api_key.txt"


class CligleError(Exception):
    """An expected, user-facing CLI error."""


def read_api_key(key_file: Path) -> str:
    """Read and validate an API key without ever printing it."""
    try:
        api_key = key_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError as error:
        raise CligleError(
            f"API key file not found: {key_file}\n"
            "Create it and put only your API key on the first line."
        ) from error
    except OSError as error:
        raise CligleError(f"Could not read API key file: {key_file}") from error

    if not api_key:
        raise CligleError(f"API key file is empty: {key_file}")
    if any(character.isspace() for character in api_key):
        raise CligleError("The API key file must contain one key with no spaces.")
    return api_key


def write_api_key(key_file: Path, api_key: str) -> None:
    """Save an API key with owner-only file permissions."""
    if not api_key:
        raise CligleError("The API key cannot be empty.")
    if any(character.isspace() for character in api_key):
        raise CligleError("The API key must contain one key with no spaces.")

    try:
        key_file.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor = os.open(
            key_file,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
            0o600,
        )
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as file:
            file.write(f"{api_key}\n")
        os.chmod(key_file, 0o600)
    except OSError as error:
        raise CligleError(f"Could not save API key file: {key_file}") from error


def set_api_key(
    key_file: Path,
    prompt: Callable[[str], str] | None = None,
) -> None:
    """Prompt for and save an API key without echoing it to the terminal."""
    hidden_prompt = prompt or getpass.getpass
    try:
        api_key = hidden_prompt("Enter your search API key: ").strip()
        confirmation = hidden_prompt("Confirm your search API key: ").strip()
    except (EOFError, OSError) as error:
        raise CligleError("Could not read the API key from the hidden prompt.") from error

    if not api_key:
        raise CligleError("The API key cannot be empty.")
    if api_key != confirmation:
        raise CligleError("The API key entries did not match.")

    write_api_key(key_file, api_key)
    print(f"API key saved to {key_file}")


def build_search_url(
    endpoint: str,
    api_key: str,
    query: str,
    engine: str = DEFAULT_ENGINE,
    page: int = 1,
) -> str:
    """Build a SerpApi URL while correctly encoding query, key, and pagination."""
    if page < 1:
        raise CligleError("The page number must be 1 or greater.")

    parts = urlsplit(endpoint)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise CligleError(
            f"Invalid search endpoint: {endpoint}\n"
            "Set CLIGLE_SEARCH_URL to the full http(s) API URL."
        )

    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params.update(
        {
            "engine": engine,
            "api_key": api_key,
            "q": query,
            "start": str((page - 1) * RESULTS_PER_PAGE),
        }
    )
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(params), parts.fragment)
    )


def _redact_api_key(text: str, request_url: str) -> str:
    """Prevent an echoed request URL from leaking the API key in an error."""
    query = dict(parse_qsl(urlsplit(request_url).query, keep_blank_values=True))
    api_key = query.get("api_key")
    if not api_key:
        return text
    return text.replace(request_url, "[request URL redacted]").replace(
        quote(api_key, safe=""), "[API_KEY REDACTED]"
    ).replace(api_key, "[API_KEY REDACTED]")


def fetch_search_results(url: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
    """Call the search endpoint and decode its JSON response."""
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "cligle/1.0",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        detail = _redact_api_key(detail, url)
        suffix = f": {detail[:240]}" if detail else ""
        raise CligleError(f"Search request failed with HTTP {error.code}{suffix}") from error
    except URLError as error:
        reason = getattr(error, "reason", error)
        raise CligleError(f"Could not reach the search API: {reason}") from error
    except TimeoutError as error:
        raise CligleError("The search API timed out after 30 seconds.") from error

    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body.decode("utf-8", errors="replace")


def _first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _result_items(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []

    for key in ("organic_results", "results", "items"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def format_results(payload: Any) -> str:
    """Format common search API response shapes for terminal output."""
    if isinstance(payload, str):
        return payload.strip() or "The search API returned an empty response."

    if not isinstance(payload, dict):
        return json.dumps(payload, indent=2, ensure_ascii=False)

    error_message = _first_text(payload, "error", "message")
    if error_message and not _result_items(payload):
        return f"API error: {error_message}"

    lines: list[str] = []
    answer_box = payload.get("answer_box")
    if isinstance(answer_box, dict):
        answer = _first_text(answer_box, "answer", "snippet", "result")
        if answer:
            lines.extend(["Answer", f"  {answer}", ""])

    items = _result_items(payload)
    for index, item in enumerate(items, start=1):
        title = _first_text(item, "title", "name") or "(untitled result)"
        link = _first_text(item, "link", "url")
        snippet = _first_text(item, "snippet", "description", "content")

        lines.append(f"{index}. {title}")
        if link:
            lines.append(f"   {link}")
        if snippet:
            lines.append(f"   {snippet}")
        lines.append("")

    if lines:
        return "\n".join(lines).rstrip()

    return json.dumps(payload, indent=2, ensure_ascii=False)


def write_results(output_directory: Path, query: str, content: str) -> Path:
    """Write results to a query-named text file without overwriting old results."""
    try:
        output_directory.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise CligleError(
            f"Could not create output directory: {output_directory}"
        ) from error

    filename_stem = re.sub(r"[^\w-]+", "_", query, flags=re.UNICODE).strip("_")
    filename_stem = filename_stem[:80] or "search"
    output_path = output_directory / f"{filename_stem}.txt"

    for suffix in range(2, 1000):
        try:
            with output_path.open("x", encoding="utf-8") as file:
                file.write(f"Query: {query}\n\n{content.rstrip()}\n")
            return output_path
        except FileExistsError:
            output_path = output_directory / f"{filename_stem}_{suffix}.txt"
        except OSError as error:
            raise CligleError(f"Could not write output file: {output_path}") from error

    raise CligleError(
        f"Could not choose an unused output filename in: {output_directory}"
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cligle",
        description="Search the web from your terminal.",
    )
    parser.add_argument(
        "query",
        nargs="*",
        help="the words you want to search for",
    )
    parser.add_argument(
        "-set",
        action="store_true",
        dest="set_key",
        help="securely save or replace the API key",
    )
    parser.add_argument(
        "--engine",
        default=DEFAULT_ENGINE,
        help=f"search engine to use (default: {DEFAULT_ENGINE})",
    )
    parser.add_argument(
        "-p",
        "--page",
        type=int,
        default=1,
        metavar="NUMBER",
        help="results page to request (default: 1)",
    )
    parser.add_argument(
        "--key-file",
        type=Path,
        default=DEFAULT_KEY_FILE,
        help="file containing the API key (default: ~/.cligle/api_key.txt)",
    )
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("CLIGLE_SEARCH_URL", DEFAULT_ENDPOINT),
        help="search endpoint; can also be set with CLIGLE_SEARCH_URL",
    )
    parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        dest="raw_json",
        help="print the raw JSON response instead of formatted results",
    )
    parser.add_argument(
        "-o",
        "--output",
        nargs="?",
        const=Path.home(),
        default=None,
        type=Path,
        metavar="DIRECTORY",
        help="save results as a .txt file; defaults to your home folder when no directory is given",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    if args.set_key:
        if args.query:
            parser.error("-set cannot be used together with a search query")
        try:
            set_api_key(args.key_file)
        except CligleError as error:
            print(f"cligle: {error}", file=sys.stderr)
            return 1
        except KeyboardInterrupt:
            print("\ncligle: setup cancelled.", file=sys.stderr)
            return 130
        return 0

    if not args.query:
        parser.error("a search query is required (or use -set to save an API key)")

    query = " ".join(args.query).strip()

    try:
        key_file = args.key_file
        if (
            key_file == DEFAULT_KEY_FILE
            and not key_file.exists()
            and LEGACY_KEY_FILE.exists()
        ):
            key_file = LEGACY_KEY_FILE
        api_key = read_api_key(key_file)
        url = build_search_url(
            args.endpoint, api_key, query, args.engine, args.page
        )
        payload = fetch_search_results(url)
    except CligleError as error:
        print(f"cligle: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\ncligle: search cancelled.", file=sys.stderr)
        return 130

    if args.raw_json:
        if isinstance(payload, str):
            output = payload
        else:
            output = json.dumps(payload, indent=2, ensure_ascii=False)
    else:
        output = format_results(payload)

    if args.output is not None:
        try:
            output_path = write_results(args.output, query, output)
        except CligleError as error:
            print(f"cligle: {error}", file=sys.stderr)
            return 1
        print(f"Saved results to {output_path}")
    else:
        print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
