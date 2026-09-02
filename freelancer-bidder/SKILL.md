---
name: freelancer-bidder
description: "Search freelancer.com projects, analyze requirements, and submit AI-generated bids/proposals."
allowed-tools: [browser-automation]
user-invocable: true
---

# Freelancer.com Bidder

Use only the browser-automation tool to navigate freelancer.com. Do NOT use web_search or web_fetch — they are unavailable.

## Browser Setup (CRITICAL — Must Follow)

Before doing anything with the browser:

1. Check browser status with `action="status"`.
2. If not ready, start the browser first. Wait for "chrome started" confirmation from logs before proceeding.
3. Then `action="tabs"` to confirm browser is responsive.
4. Only then proceed to open URLs.

Use `timeoutMs: 60000` for the first `action="open"` call to give Chrome time to start.

## Workflow

1. Ask user for search keywords.
2. Start browser if not running (use status check first).
3. Open freelancer.com search page with a generous timeout (60s).
4. Use snapshot to read the page content.
5. Present project list to user for selection.
6. For the selected project, navigate to its detail page.
7. Generate and submit a proposal.

## Notes

- The browser starts asynchronously. Always check status before using it.
- freelancer.com pages are JavaScript-rendered, so web_fetch cannot read them — only browser-automation works.
- If the first attempt fails, retry once with a fresh browser check.
