# Kalium

The canonical distribution for the Kalium Python library.

An independent, unofficial third-party client for the KaliumLabs API. It is
not affiliated with, sponsored by, or endorsed by KaliumLabs.

## Install

```bash
python -m pip install kalium
```

## Import

```python
import kalium
```

This distribution is licensed under the MIT License; see `LICENSE`.
Maintained by [Hiro Dev](https://github.com/hiroxnull).

## Quick start

```python
from kalium import KaliumClient

with KaliumClient() as client:  # Reads KALIUM_API_KEY from the environment.
	page = client.list_labs(category="cryptography", status="active", limit=20)
	print(f"Found {page['total']} labs")

	for lab in client.iter_labs(category="cryptography", status="active"):
		print(f"[{lab['difficulty']}] {lab['name']} ({lab['points']} points)")
```

Pass `api_key="..."` to `KaliumClient` instead of setting `KALIUM_API_KEY` when
you prefer explicit configuration. The client does not load `.env` files by
itself.

## Inline API key

You can pass a key directly when experimenting locally:

```python
from kalium import KaliumClient

with KaliumClient(api_key="YOUR_KALIUM_API_KEY") as client:
	page = client.list_labs(limit=5)
	print(f"Found {page['total']} labs")
```

Replace the placeholder with your key. Never commit a real API key or publish
it in source code; use an environment variable for shared or public code.

Available methods include `list_labs`, `iter_labs`, `get_lab`, `get_lab_image`
and `get_stats`. The client validates pagination locally, returns the API's
original dictionaries to preserve fields that vary between labs, and raises
typed exceptions such as `AuthenticationError`, `NotFoundError` and
`RateLimitError`. It retries rate limits and transient server failures by
default; set `max_retries=0` to receive errors immediately. Rate-limit retries
respect `Retry-After` and may wait for the server's requested delay. The default
`max_retry_wait` is 300 seconds; if the server asks for a longer wait, the
client raises the typed error instead of blocking or retrying too early.

`iter_labs` removes overlapping records by ID and raises `InvalidResponseError`
if the API repeats a page without progress or returns a malformed lab item.