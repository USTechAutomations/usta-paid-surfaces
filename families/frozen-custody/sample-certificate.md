# Frozen Model Custody — sample certificate

Status: SAMPLE. Not signed. Not a paid pin.

## What this paper claims

On our machine, this exact model and these exact settings produced the same bytes five times for one sealed input. It does **not** claim the answer is true, safe, legal, or useful.

## Pin

| Field | Value |
|---|---|
| Product | Frozen Model Custody |
| Pin id | SAMPLE-2026-09-01-s2 |
| Model name served | `qwen38-s2` |
| Model root | `unsloth/Qwen3.8-27B-NVFP4` |
| Weights revision | `7d6f8d4d72f56b92b3cdbf22f156b90e1bab0108` |
| Engine fingerprint | `vllm-0.25.1-9f488e66` (returned on all 5 calls) |
| max_model_len (recipe) | 32768 |
| max_num_seqs (recipe) | 4 |
| gpu_memory_utilization (recipe) | 0.60 |
| prefix caching (recipe) | on |
| Offline weights | `HF_HUB_OFFLINE=1` (recipe) |

## Weights fingerprint (read-only)

Cache: read-only mount at `/mnt/glm-weights`.

Snapshot:

`/mnt/glm-weights/hub/models--unsloth--Qwen3.8-27B-NVFP4/snapshots/7d6f8d4d72f56b92b3cdbf22f156b90e1bab0108`

| File | Bytes | SHA-256 first 1 MiB | SHA-256 last 1 MiB |
|---|---|---|---|
| `model.safetensors` | 22,568,192,096 | `c8d2d06d4cff3588cabdb630d6a060b3d72162d233ec6b20f975a11461507d3a` | `83cda4b4730bdf6ae81dd1d4d94958ca0e6ff7f41e23564b97770fac6ef2d841` |
| `model_mtp.safetensors` | 849,400,392 | `f43c6b807aa1c068a7210a0b88c5bf28b74befc3a447fabe33f7b93952361543` | `5e1360631ecdbdfabf877bd415a4a0b75f2590f0a6139fbbb7ab22879bc99da1` |

Full-file SHA-256 of the 22 GB weights: **UNKNOWN** this run (not rehashed). Hugging Face blob id for `model.safetensors`: `c473512c70eace07e2256fe9fd76596ac03e3295bee7d54cfb72676416afcc05`.

`config.json` SHA-256: `1b3c71868d1299e52df6fc907deb202d5132b1ef0f72aae0ef6d15185dd53a5c` (22,564 bytes).

The model is Apache License 2.0. We host a frozen copy on our machine. We do not sell a weights download. Licensor provides the Work on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, including FITNESS FOR A PARTICULAR PURPOSE.

## Sealed request

| Field | Value |
|---|---|
| Prompt (UTF-8) | `Reply with exactly five words: frozen model custody holds.` |
| Input SHA-256 | `864227ab119fff2bc364478287b933b4a1f3eeb817b42809f627a470c0710f83` |
| temperature | 0 |
| seed | 42 |
| max_tokens | 64 |
| endpoint | `POST /v1/chat/completions` |

## Sealed answer

| Field | Value |
|---|---|
| Runs | 5 |
| Identical | **true** (1 unique hash) |
| Output SHA-256 (message content UTF-8) | `67266ea3e0c06a4259669d9ce46fbad22104206059166eb73d405fa8cd7e3638` |
| Content length | 285 bytes each run |
| finish_reason | `length` each run (hit the 64-token cap; truncated bytes still matched) |
| Timestamps (UTC) | 2026-09-01T21:50:44Z … 21:51:12Z |

Five identical output SHA-256 lines:

```
67266ea3e0c06a4259669d9ce46fbad22104206059166eb73d405fa8cd7e3638
67266ea3e0c06a4259669d9ce46fbad22104206059166eb73d405fa8cd7e3638
67266ea3e0c06a4259669d9ce46fbad22104206059166eb73d405fa8cd7e3638
67266ea3e0c06a4259669d9ce46fbad22104206059166eb73d405fa8cd7e3638
67266ea3e0c06a4259669d9ce46fbad22104206059166eb73d405fa8cd7e3638
```

Engine fingerprint on all five: `vllm-0.25.1-9f488e66`.

Machine record: `sample-determinism.json`.

## Promise vs not

**We promise (when this is a paid pin):** If a re-run of a sealed input on your pin is not the same bytes, that month is refunded. We do not guarantee the answer is correct. The monthly paper still shows the same first/last 1 MiB weights hashes and the same settings.

**We do not promise:** that the answer is correct. That a regulator will accept it. That another vendor, GPU, or software version will match. That the model is safe. Uptime this run: UNKNOWN (not measured).

## Signature

```
USTA-SIGN: NOT SIGNED — sample only.
Operator applies the company key. This file is a format demo.
Signed-over: pin table + weights table + input hash + output hash + date.
Date: 2026-09-01
```
