# HN daily podcast pipeline

The full pipeline behind [Turning Hacker News into a daily podcast with ADK 2, Gemini TTS, and Cloud Run jobs](../hn-daily-podcast.md): fetch the last 26 hours of Hacker News, curate, digest and fact-check per story, write and fact-check the script, render segmented TTS audio, and publish an mp3 plus RSS feed to a Cloud Storage bucket.

## Files

- [pipeline.py](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/hn-daily-podcast-code/pipeline.py) - the entire pipeline: the graph, the agents and their prompts, fact-checking, TTS rendering, and publishing
- [Dockerfile](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/hn-daily-podcast-code/Dockerfile) - container image for the Cloud Run job
- [requirements.txt](https://github.com/ykdojo/awesome-agents-on-google-cloud/blob/main/hn-daily-podcast-code/requirements.txt) - Python dependencies

## Environment

- `GEMINI_API_KEY` - key for the TTS calls (free tier works)
- `GOOGLE_GENAI_USE_ENTERPRISE=TRUE` plus application default credentials - for the text models, billed to your Cloud project
- `GOOGLE_CLOUD_LOCATION=global`
- `PUBLISH_BUCKET` - Cloud Storage bucket name; unset writes to `./out` locally
- `STORY_CHECK=1` - per-story digest fact-checking (recommended; this is the A/B winner)
- `DRY_RUN=1` - stop before TTS and publishing, for cheap logic tests

## Deploy and schedule

```bash
gcloud builds submit --tag $REGION-docker.pkg.dev/$PROJECT/$REPO/hn-digest .
gcloud run jobs create hn-digest --image $IMAGE --task-timeout 3600 \
  --set-env-vars "GOOGLE_GENAI_USE_ENTERPRISE=TRUE,GOOGLE_CLOUD_LOCATION=global,PUBLISH_BUCKET=$BUCKET,STORY_CHECK=1,GEMINI_API_KEY=$KEY"
gcloud scheduler jobs create http hn-digest-morning \
  --schedule="0 6 * * *" --time-zone="America/Los_Angeles" \
  --uri="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/hn-digest:run" \
  --oauth-service-account-email=$SERVICE_ACCOUNT
```
