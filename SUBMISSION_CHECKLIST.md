# AgriLens submission checklist

## Package completed
- Root README includes theme, user, business use, Egypt rationale, sources, team and execution commands.
- Root AgriLens_PoC.ipynb reads the 615-row example and reruns the current method.
- Existing notebooks have corrected repository paths.
- requirements.txt pins versions from the executed Python 3.12.14 environment.
- Example input, CSV results, GeoJSON, figures and presentation/AgriLens_PoC_Pitch.pdf are included.
- 13 model regression tests pass. All notebook cells pass in fresh in-process IPython kernels.

## Remaining team actions before submitting
1. Run the standard nbconvert command in README on your machine, or check the included GitHub Actions notebook job after pushing. Standard kernel transport is unverified here because this execution environment prohibits local sockets.
2. Publish the extracted folder CONTENTS to the intended GitHub repository, so README.md, requirements.txt and AgriLens_PoC.ipynb are at the repository root. Verify evaluator access in a signed-out window. No real repository URL was supplied or published in this task.
3. Upload the pitch PDF and enter the repository URL and team details in the organiser platform. Check the final confirmation and retain the submission receipt. No platform submission was performed here.
4. Use the organiser announcement in your account as the deadline authority. The supplied target is 11 October 2026, 22:59 Jordan / 23:59 Dubai. Public materials checked during this audit contain conflicting dates and did not independently confirm the cutoff time. Do not wait for the later date.

## Important presentation distinctions
- Current v1.2 forecast screen: 16 raw flags, 5 suspected-scene holds, 11 candidates.
- Dashboard median-deviation validation: 36 raw flags, 13 holds, 23 remaining observations (14 positive, 9 negative).
- Earlier 15 / 5 / 10 figures are outdated for the current model.
- EMIT is genuine hyperspectral data, not Satellite 813 data. It is exploratory and is not part of the current temporal forecast feature set.
- No verified damage labels, no dust/drought classification accuracy, and no measured water savings.

This checklist addresses the requirements quoted in the user-provided audit. The original submission-guide PDF was not included in this attachment, so full automated-rule compliance cannot be certified from that guide.
