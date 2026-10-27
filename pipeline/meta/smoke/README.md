# Meta model smoke tests

One call to each model the project uses, to check the keys work and to see what each one returns before the pipeline is built on it.

| Script | Model | Checks |
|---|---|---|
| `01_spark_text.py` | Muse Spark 1.3 | Key, latency, token usage |
| `02_spark_tools.py` | Muse Spark 1.3 | Tool calling with Studio-like tools: arguments, calls per turn, continuing after results |
| `03_image_generate.py` | Muse Image 1.0 | A product photo of a fictional brand (`out/product.png`, used by 04, 05, 07) |
| `04_spark_vision.py` | Muse Spark 1.3 | Reading the photo into brand-analyst JSON |
| `05_sam_segment.py` | SAM 3.1 | Masks for the product, cap and label; overlay; the silhouette's profile |
| `06_voice_transcribe.py` | Muse Voice Transcribe 1.0 | A spoken brief to text (makes the audio with Windows' speech synthesizer, or pass a WAV) |
| `07_spark_open_baseten.py` | Muse Spark Open (Baseten) | Text and vision on the open-weight model |

## Run

From the repo root:

```
python -m venv .venv
.venv\Scripts\python -m pip install -r pipeline\requirements.txt
copy .env.example .env          (then fill in MODEL_API_KEY and BASETEN_API_KEY)
.venv\Scripts\python pipeline\meta\smoke\run_all.py
```

Each script also runs on its own. Results go to `pipeline/meta/smoke/out/` (git-ignored): `summary.md`, the raw responses, `product.png`, `05_sam_overlay.png`, `05_profile_px.csv`. A test without its key, or without `product.png`, is skipped rather than failed. 06 needs ffmpeg on the PATH.
