# Public web availability

The competition URL remains https://sonarnet.streamlit.app/.

`check-web-awake.yml` opens the public site in Chromium every six hours, at
00:17, 06:17, 12:17 and 18:17 UTC (07:17, 13:17, 19:17 and 01:17 in Vietnam).
It can also be started with GitHub Actions **Run workflow**.

The checker clicks the standard public wake button if present, then requires
the research heading, observation navigation, and received messages on a live
Streamlit websocket. These signals must remain present for ten seconds.
An HTTP 200 or the static loading shell alone cannot pass the check.
The browser wait is bounded to seven minutes, with at most two wake clicks.
Resource-limit and application errors are failures, not successful wake-ups.

Each run saves `result.json` and a viewport screenshot in its seven-day artifact,
plus a concise GitHub job summary. It never records cookies, websocket payloads,
authentication state or private browser sessions. No credentials are required.
Only the public landing page is visited; there is no inference, data write,
empty commit, production reboot, or interaction with the observation data.
The worker has read-only repository permissions and sparse-checks out two files,
not the satellite image archive. Its concurrency group is separate from scanning.

## Verification over more than 12 hours

After the first successful manual run, compare at least three scheduled results
over a period exceeding 12 hours. Check `status`, `checked_at`, `wake_clicks`,
and `websocket_messages`. A nonzero wake count means sleep was encountered and
recovered, not prevented. Passing scheduled checks establish availability only
at those sampled times; they cannot prove uninterrupted uptime between checks.
Keep failures visible. GitHub workflow notifications depend on account settings.

## Limits

This is a best-effort browser health check, not an always-on hosting guarantee.
GitHub can delay or skip scheduled jobs. Public-repository schedules may disable
after 60 days without repository activity. Streamlit can change its policy or
restart the app independently. Do not rely on this for emergency operations.
If it repeatedly fails, inspect the screenshot/error code and stop blind retries;
request support from Streamlit for the research use case instead.

Sources:
- https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app#app-hibernation
- https://playwright.dev/python/docs/ci
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule
- https://docs.github.com/en/actions/how-tos/manage-workflow-runs/disable-and-enable-workflows
