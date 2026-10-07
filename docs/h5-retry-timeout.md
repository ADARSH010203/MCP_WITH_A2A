# H5: Retry and Timeout Hardening

Specialist execution now uses bounded retries instead of unbounded repeated calls.

The retry policy provides:

- exponential backoff
- bounded positive jitter
- a maximum backoff
- optional HTTP `Retry-After` support
- a total retry timeout window

Timeout results are retryable when attempts remain, but the total timeout prevents retries from extending indefinitely.

Remote A2A retries reuse one operation task ID. This preserves the A2A task manager's idempotency behavior and prevents a transient network failure from creating duplicate remote tasks.

Permanent failures are not retried. Retry attempts remain subject to the per-task call budget.

Configuration:

`A2A_SPECIALIST_MAX_RETRIES` controls retries.

`A2A_SPECIALIST_RETRY_BACKOFF_SECONDS`, `A2A_SPECIALIST_RETRY_MAX_BACKOFF_SECONDS`, and `A2A_SPECIALIST_RETRY_JITTER_RATIO` control retry delay.

`A2A_SPECIALIST_TOTAL_TIMEOUT_SECONDS` caps the complete retry window.

Streaming specialist calls continue to use a total streaming timeout and are not automatically replayed.
