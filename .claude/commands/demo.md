---
description: Run the 5-step judge demo end to end with curl against the TEST database and print a readable transcript
---

1. Use the **test** database only (see `/run-tests` step 1). Apply `migrations/001_crop_rescue.sql` and `migrations/002_demo_seed.sql` to it. Never use the main Supabase database here.
2. Start `CR_DATABASE_URL=$CR_TEST_DATABASE_URL uvicorn dev_app:app --port 8000` in the background.
3. Run the 5 demo steps from the "Demo script" section of CLAUDE.md with curl, passing `?farmer_id=demo-farmer-1`. (In dev_app the farmer comes from this query parameter; in the main backend it comes from the login.) For each step, print:
   - the step name
   - the key fields only (status, remaining_hours, spoil_eta, alert title, top-3 buyer reasons)
4. Check each expected result. Tomato at 30 °C ≈ 68 h FRESH; cold tomato 168 h FRESH; spinach AT_RISK immediately; tomato after +12 h is AT_RISK with 3 matches; after SOLD, no new alerts. Also check that `?farmer_id=demo-farmer-2` can't see farmer 1's lots (404).
5. Stop the server. Report PASS/FAIL per step.

Also save the transcript to `docs/demo_transcript.md` so the team can rehearse from it.
