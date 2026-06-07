# Memory Index

- [Always push after edits](always-push-after-edits.md) — commit + push to GitHub after every code change, no need to ask.
- [db_helpers 60s cache](db-helpers-60s-cache.md) — get_all_* readers are TTLCache'd 60s; call invalidate_* after writes or new items show up delayed.
- [Supabase schema is manual](supabase-schema-manual.md) — no DB access; column/table changes must be handed to the user as SQL for the Supabase SQL Editor.
