# Lessons Learned


## v3.0-dev (2026-07-25T18:17:23+02:00)\n- problems discovered: pipeline service showed failed state from historical run before symlink promotion.\n- root causes: execution happened before /opt/carhunter/current was switched to v2.9, creating stale failure history tied to v2.8 runtime paths.\n- resolutions: operational validation executed manual pipeline on current target and confirmed v2.9 runtime/database paths.\n- preventive actions: enforce release ordering and explicit post-switch pipeline validation prior to release closure.
