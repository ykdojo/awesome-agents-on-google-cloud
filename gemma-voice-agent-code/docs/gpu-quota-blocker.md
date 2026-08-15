# Blocker log: Cloud Run GPU quota stuck at 0 on a new account

**Date:** 2026-07-07. **Status:** open. Brand-new billing account (trial signed up, activation
prepayment paid, upgraded to paid the same day), fresh project with billing linked.

## Repro

**1. GPU deploy** (per the [docs](https://docs.cloud.google.com/run/docs/configuring/services/gpu),
the first L4 deploy in a region should auto-grant 3 GPUs of quota):

```sh
cd hello-gpu
gcloud run deploy hello-gpu --source . --region us-central1 \
  --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy \
  --cpu 4 --memory 16Gi --max-instances 1 --allow-unauthenticated
```

```
ERROR: (gcloud.run.deploy) ... You do not have quota for using GPUs without zonal redundancy.
```

Same with `--gpu-zonal-redundancy`: `You do not have quota for using GPUs with zonal redundancy.`

**2. Quota request via API** (also tried `NvidiaL4GpuAllocPerProjectRegion`, and regions
`us-east4`, `europe-west1`):

```sh
gcloud beta quotas preferences create --service=run.googleapis.com \
  --quota-id=NvidiaL4GpuAllocNoZonalRedundancyPerProjectRegion \
  --preferred-value=1 --dimensions=region=us-central1 \
  --project=<project id> --email=<account email>
```

```
"grantedValue": "0",
"stateDetail": "We cannot grant the preferred quota '1' ... at this moment. '0' was granted."
```

**3. Quota request via console:** IAM & Admin → Quotas & System Limits → filter
`NvidiaL4GpuAllocNoZonalRedundancy` + `us-central1` → row menu (⋮) → Edit quota.
The panel refuses input:

> Enter a new quota value between 0 and 0. Based on your service usage history, you are not
> eligible for a quota increase at this time.

![Cloud console quota edit panel locked at 0](cloud-run-gpu-quota-blocked.png)

## Diagnosis

Free-trial accounts [can't use GPUs or request quota increases](https://docs.cloud.google.com/free/docs/free-cloud-features).
Upgrading to paid is supposed to lift that immediately, but there is a trust/propagation lag
(roughly 24 to 48 hours per support replies; [one report](https://discuss.google.dev/t/cloud-run-gpu-quota-not-activated-after-50-hours-on-paid-account/323795)
still waited at 50+ hours; [same wall here](https://discuss.google.dev/t/300-free-trial-is-useless-without-gpu-quota-my-trial-period-is-wasting-away/290091)).

## Escalation attempts

I also tried escalating this to sales and support, but none of the options I tried quite worked.

## Update (2026-07-08/09)

The error changes with how you deploy. Verified in all five publicly available L4 regions;
behavior is identical everywhere:

**Creating a new GPU service** fails on GPU quota, as in the repro above.

**Updating an existing (CPU-only) service to GPU** gets past that check and fails on memory.
Same command as the repro; the difference is that `hello-gpu` already existed as a CPU-only
service:

```sh
gcloud run deploy hello-gpu --source . --region us-central1 \
  --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy \
  --cpu 4 --memory 16Gi --max-instances 1 --allow-unauthenticated
```

```
Quota violated:
MemAllocPerProjectRegion requested: 51539607552 allowed: 42949672960
```

That's 48 GiB requested vs 40 GiB allowed: Cloud Run requires at least 16 GiB of RAM on any
instance with a GPU attached, and the
[first-deploy auto-grant](https://docs.cloud.google.com/run/docs/configuring/services/gpu)
comes as a fixed bundle of 3 GPUs.

Requests to raise the memory cap are denied; the quotas API reports it as ineligible:

```sh
gcloud beta quotas info describe MemAllocPerProjectRegion \
  --service=run.googleapis.com --project=<project id> \
  --format="yaml(quotaIncreaseEligibility)"
```

```
quotaIncreaseEligibility:
  ineligibilityReason: NOT_ENOUGH_USAGE_HISTORY
```

**Updating a service that already has the resources** bypasses the memory check entirely.
Deploy CPU-only with the GPU minimums (4 CPU, 16 GiB) first, then add only the GPU:

```sh
gcloud run deploy hello-gpu-mem --image <image> --region us-central1 \
  --cpu 4 --memory 16Gi --max-instances 1 --allow-unauthenticated

gcloud run deploy hello-gpu-mem --image <image> --region us-central1 \
  --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy \
  --cpu 4 --memory 16Gi --max-instances 1 --allow-unauthenticated
```

The second deploy passes validation and creates the revision, then fails at provisioning:

```
Quota exceeded for total allowable count of GPUs per project per region.
```

**Bottom line:** no path grants any GPU quota. Per the
[docs](https://docs.cloud.google.com/run/docs/configuring/services/gpu), the first GPU
deployment in a region automatically grants 3 GPUs of quota, no request needed. That never
happened here, even after a GPU revision was created.

## Update (2026-07-29): still blocked, 22 days after upgrading to paid

Re-tested with a fresh new-service deploy using the prebuilt hello image (no build,
fails at validation if quota is still 0):

```sh
gcloud run deploy gpu-quota-probe --image=us-docker.pkg.dev/cloudrun/container/hello \
  --region us-central1 --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy \
  --cpu 4 --memory 16Gi --max-instances 1 --no-allow-unauthenticated
```

```
ERROR: (gcloud.run.deploy) ... You do not have quota for using GPUs without zonal redundancy.
```

Identical error to Jul 7. Quota increase eligibility is also unchanged on both quotas:

```
NvidiaL4GpuAllocNoZonalRedundancyPerProjectRegion: NOT_ENOUGH_USAGE_HISTORY
MemAllocPerProjectRegion:                          NOT_ENOUGH_USAGE_HISTORY
```

So the "24-48 hour trust propagation" explanation is ruled out: three weeks on a paid
account with real (CPU) Cloud Run usage, and both the auto-grant and the manual request
paths remain closed. This looks like an account-trust tier gate, not a propagation lag.
(The probe service was not created; nothing to clean up.)

### Full matrix re-run, same day

Every path from the July repro, re-tested:

| Path | Result |
|------|--------|
| New service, `--no-gpu-zonal-redundancy`, us-central1 | validation error, no quota (unchanged) |
| New service, `--gpu-zonal-redundancy`, us-central1 | validation error, no quota (unchanged) |
| New service, us-east4 / europe-west1 / asia-southeast1 / europe-west4 | identical validation error in all four (unchanged) |
| Update `hello-gpu-mem` (already 4 CPU / 16 GiB) to add GPU | passes validation, fails at provisioning: `Quota exceeded for total allowable count of GPUs per project per region` (unchanged) |
| Quotas API: new preference request | rejected as duplicate; the existing preference still shows `grantedValue: 0` |
| `quotaIncreaseEligibility` on GPU + memory quotas | still `NOT_ENOUGH_USAGE_HISTORY` |

All existing quota preferences on the project (GPU no-zonal ×3, GPU zonal, compute
`GPUS-ALL-REGIONS`, memory) remain granted 0 or capped. `hello-gpu-mem` was restored
to CPU-only afterward (revision 00009).

## Update (2026-08-11 late): partial thaw - GPU quota granted, memory cap remains

Re-test in a different, GPU-proven project (one that had deployed RTX 6000 Pro
services all day under a promotional credit billing account) after relinking it
to this personal billing account:

- `NvidiaRtxPro6000GpuAllocNoZonalRedundancyPerProjectRegion` (us-central1): **granted**
  (nonzero). The July "GPU quota stuck at 0" wall is gone on this account.
- `MemAllocPerProjectRegion` (us-central1): **40 GiB**, while the RTX 6000 Pro tier
  requires 80 GiB per instance. Waking an existing GPU service fails at instance start:
  `The request failed because the project exceeded its quota limit for
  run.googleapis.com/mem_allocation recently.`
- Increase requests via the Quotas API: preferred 200 GiB and preferred 80 GiB both
  denied instantly ("We cannot grant the preferred quota ... at this moment.
  '42949672960' was granted.").

Same project, same services, same day: boots fine on the credit billing account,
memory-blocked on the personal one. The quota follows the billing account, and the
gate has shifted from the GPU allocation itself to the memory floor the GPU tier
mandates.
