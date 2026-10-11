# AgriLens — Final Validation Package (Rama)

Start with `NOUR_HANDOFF.md` (what to plot and how to word it), then `AgriLens_Validation_Report.md` (evidence).

Reproduce: `python scripts/build.py <team_dataset_root> <out_dir>` then `scripts/report.py`, `scripts/handoff.py`, `scripts/verify.py` (needs pandas, numpy, matplotlib, pyarrow, pyproj). `verification/verification_log.json` holds the last automated check results.

Scope: team data only. Flags are screening signals, not verified damage; no dust-vs-drought accuracy is claimed. Supersedes `AgriLens_Validation_Final` and `AgriLens_Validation_Corrected`.
