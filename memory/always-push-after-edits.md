---
name: always-push-after-edits
description: User wants every code change committed and pushed to GitHub automatically
metadata:
  type: feedback
---

After making any code edit in the BombaVPN/GalaxyVPN project, commit and push to GitHub (origin/main) without being asked each time.

**Why:** The user explicitly said "في كل مرة تعدل فيها اي شيئ قم برفع التحديثات" (every time you edit anything, push the updates).

**How to apply:** Once a logical change is complete and verified (py_compile passes for app.py), stage the relevant files (not the throwaway patch_*.py scripts), commit with a descriptive message, and `git push origin main`. The repo redirects from BombaVPN.git to GalaxyVPN.git — push still works.
