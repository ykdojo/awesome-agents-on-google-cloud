# hello-gpu

Smallest possible Cloud Run GPU check: an HTTP server that says hello and prints `nvidia-smi`.
Deploying this once also auto-grants the L4 GPU quota in the region.

```sh
gcloud run deploy hello-gpu \
  --source . \
  --region us-central1 \
  --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy \
  --cpu 4 --memory 16Gi \
  --max-instances 1 \
  --allow-unauthenticated
```

Then `curl` the service URL and you should see the L4 in the `nvidia-smi` table. Scale-to-zero is
the default, so an idle service costs nothing.
