---
name: db-helpers-60s-cache
description: get_all_* readers in db_helpers.py are TTLCache'd for 60s; invalidate after writes or new items appear delayed
metadata:
  type: project
---

`db_helpers.py` wraps `get_all_users / get_all_servers / get_all_messages / get_all_subscriptions / get_all_pricing_rules / get_all_source_links` in a 60-second `TTLCache`. After any write (insert/update/delete) the next read returns STALE cached data, so newly added/removed items appear to "take a long time" (up to 60s) to show in the admin dashboard.

**Fix pattern:** call the matching `invalidate_*()` helper in `db_helpers.py` immediately after the supabase write. These helpers (`invalidate_servers`, `invalidate_pricing_rules`, `invalidate_source_links`, `invalidate_subscriptions`, `invalidate_users`, `invalidate_messages`) were added to clear the cache so the next read is fresh.

**How to apply:** any new admin mutation route must import and call the relevant `invalidate_*()` after the write, otherwise the SPA-style `fetchDashboardSync` / `fetchPricingRules` refresh will show stale data. Related: the admin dashboard does targeted JSON syncs instead of full reloads (see templates/admin_dashboard.html `submitAjaxForm`).
