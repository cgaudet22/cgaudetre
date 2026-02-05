# Video Pipeline Runbook

## Cleanup

Cleanup is **gated** and must follow this exact sequence after each upload run:

1. **Verify YouTube processing and playback**
   - Confirm the uploaded video has finished YouTube processing.
   - Confirm playback is available (video is watchable from the published URL).

2. **Persist a run record**
   - Write a durable run record before any deletion with:
     - topic
     - YouTube video ID
     - public URL
     - artifact checksum (for final output)
     - key timestamps (build, upload, verification, sheet-write times)

3. **Retention window for artifacts**
   - Keep `final_video` and key intermediates for a configurable retention period.
   - Recommended default window: **24–72 hours**.
   - Do not hard-delete artifacts before this retention period elapses.

4. **Delete only after full success**
   - Deletion is allowed only when both conditions are true:
     - verification checks pass (processing + playback)
     - metadata has been successfully written back to Google Sheets

### Failure-path policy (recoverability)

If upload or Google Sheets metadata update fails:

- **Do not delete** `final_video` or intermediates.
- Mark the run state as **recoverable**.
- Preserve all run metadata and artifact references needed for retry/reconciliation.
