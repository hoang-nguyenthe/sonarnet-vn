# Deployment: public viewer, separate workers

The root Dockerfile runs the existing public viewer on port 7860 as UID 1000,
compatible with Hugging Face Docker Spaces. It does not train a model, fetch
new Sentinel scenes, or require Copernicus/GFW credentials. Those operations
remain in the GitHub refresh workflow and the local training process.

## Local verification

```
docker build -t sonarnet-viewer .
docker run --rm -p 7860:7860 --memory=4g --cpus=2 sonarnet-viewer
```

Open http://localhost:7860 and test imagery, candidate review, session export,
and evidence download. Measure peak memory under concurrent sessions before
claiming any visitor capacity. More hosting RAM does not fix unbounded data.

## Free Space

Create a Docker Space with CPU Basic hardware. The repository README metadata
declares Docker and port 7860. Publish only reviewed runtime files and verified
public assets; never upload the working directory wholesale. `.dockerignore`
protects the Docker build context, **not** files uploaded to a Space repository.

Do not enable paid hardware or persistent storage without owner approval.
Free Spaces sleep when idle; runtime filesystem changes are disposable.
User notes must be exported before closing the session. The original public
image assets remain in source storage, not exclusively on the runtime disk.

## Update contract

A successful GitHub push alone does not update a separate Space repository.
Repository synchronization must be configured and verified after the owner's
Space is available. Until then this is a deployment package, not a completed
hosting migration. Keep the old endpoint until the new URL passes browser
tests with current imagery and provenance.

## Outstanding scaling work

- Move imagery out of Git history into dedicated versioned object storage.
- Publish compact, prevalidated geographic data for the viewer; perform full
  shoreline masking and inference offline.
- Load imagery and candidate details by viewport; do not embed all images.
- Independently validate the detector on Vietnamese observations before
  claiming operational vessel identification.

Official Docker Spaces documentation:
https://huggingface.co/docs/hub/spaces-sdks-docker
