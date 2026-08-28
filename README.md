# cligle

`cligle` is a small Python command-line based Google search program. It sends requests in
this shape to SerpAPI:

```text
https://serpapi.com/search.html?engine=google&start=[NUM]&q=[QUERY]&api_key=[API_KEY]
```
Perfect for people who don't want to leave the terminal to search. Available on PyPI.

![PyPI Version](https://img.shields.io/pypi/v/cligle)



## Setup

1. Add your API key securely with:

   ```bash
   cligle -set
   ```

   The key is entered twice with hidden input and saved to
   `~/.cligle/api_key.txt`. Running the command again replaces the saved key.
2. If you need to use a different SerpApi endpoint, set it with
   `CLIGLE_SEARCH_URL`:

   ```bash
   export CLIGLE_SEARCH_URL="https://your-provider.example/search"
   ```

The packaged CLI stores the key at `~/.cligle/api_key.txt`. You can use a
different location with `--key-file`. The project's local `api_key.txt` is
also supported for development and is ignored by Git.

No third-party Python packages are required.

## Usage

After installing the package, the same command is available from anywhere:

```bash
python3 -m pip install cligle
cligle "python argparse tutorial"
```

The exact short form also works:

```bash
cligle query
```

Multiple words do not need quotes:

```bash
cligle python argparse tutorial
```

Open a specific results page with `-p` or `--page`:

```bash
cligle "python argparse tutorial" --page 2
cligle "python argparse tutorial" -p 3
```

Page numbers start at `1`. If no page is specified, page `1` is requested.
SerpApi uses a zero-based result offset internally, so page 1 sends
`start=0`, page 2 sends `start=10`, page 3 sends `start=20`, and so on.

Useful options:

```bash
cligle -set --key-file /path/to/api_key.txt
cligle "latest Python news" --engine google
cligle "latest Python news" --page 2
cligle "latest Python news" --key-file /path/to/api_key.txt
cligle "latest Python news" --json
```

Save results to a chosen directory:

```bash
cligle "latest Python news" -o ./results
```
Long form:
```bash
cligle "latest Python news" --output ./results
```

If `-o` or `--output` is used without a directory, the text file is saved in
your home folder:

```bash
cligle "latest Python news" -o
cligle "latest Python news" --output
```

The output filename is based on the query, such as `latest_Python_news.txt`.
Existing files are preserved by adding a number to the next filename.

The formatter recognizes common `organic_results`, `results`, `items`, and
`answer_box` response fields. The `--json` option is available when the API
returns a response shape that needs custom handling.
