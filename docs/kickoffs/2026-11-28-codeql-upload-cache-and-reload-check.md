# Kickoff: two review findings on code already on main

CodeRabbit reviewed #1099, which carries `main` into `uom-rebuild`, and
raised two findings about code that is already on `main`. The owner's
instruction, 2026-11-28: "yes, open the pull request onto main".

1. `.circleci/config.yml` (from #1098): the upload job, which holds the
   upload token, takes the CodeQL program from a cache that other jobs write.
   It must download and check the pinned bundle itself.
2. `frontend/src/main.jsx` (from #1096): the handler for Vite's preload error
   reloads the page for any failed import. Check that the error means a
   stale build before reloading.

Fix both on `main` by pull request, so `uom-rebuild` gets them by a merge and
the two branches do not differ.
