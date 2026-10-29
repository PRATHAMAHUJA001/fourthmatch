# Model Notes — verified working shapes (from scripts/smoke_models.py)

All shapes below were verified live against `https://api.meta.ai/v1` with the key in
repo-root `.env`. **Do not guess shapes elsewhere — copy from here.** All model IDs come
from `.env` (`PERCEPTION_MODEL`, `DECISION_MODEL`, `COMPILER_MODEL`, `BULK_MODEL`,
`WONDER_MODEL`, `SEG_MODEL`, `IMAGE_MODEL`, `VOICE_MODEL`), never hardcoded.

Setup (everywhere):

```python
from openai import AsyncOpenAI
client = AsyncOpenAI(base_url="https://api.meta.ai/v1", api_key=os.environ["MODEL_API_KEY"])
# Sync `OpenAI(...)` with the same arguments also works. ALWAYS Responses API,
# never chat.completions.
```

## 1. List models — GET /v1/models

Request: `GET https://api.meta.ai/v1/models` with `Authorization: Bearer $MODEL_API_KEY`
(or `client.models.list()`).

Response: `{"object": "list", "data": [{"id": ...}, ...]}` — 9 models on this key, sorted
newest-first:

```
muse-wonder-1.0, sam-3.1, muse-spark-1.3-contributor, muse-voice-transcribe-1.0,
muse-spark-1.3, muse-image-1.0, muse-spark-1.2-contributor, muse-spark-1.2, muse-spark-1.1
```

Assert the IDs your code needs are present before calling them; availability is per-key.

## 2. muse-spark-1.3 — Responses, strict structured JSON

Request (`client.responses.create`):

```python
resp = await client.responses.create(
    model=os.environ["DECISION_MODEL"],          # muse-spark-1.3
    reasoning={"effort": "high"},
    input="Confirm the smoke test: set ok to true and message to 'pong'.",
    text={"format": {
        "type": "json_schema",
        "name": "smoke_check",
        "schema": {
            "type": "object",
            "properties": {"ok": {"type": "boolean"}, "message": {"type": "string"}},
            "required": ["ok", "message"],
            "additionalProperties": False,
        },
        "strict": True,
    }},
)
data = json.loads(resp.output_text)   # strict parse; raises if not valid JSON
```

Verified response: `resp.output_text == '{"ok": true, "message": "pong"}'`,
`resp.usage` = `input_tokens=23, output_tokens=227 (reasoning_tokens=207), total_tokens=250`
(shape: `resp.usage.input_tokens_details.cached_tokens`,
`resp.usage.output_tokens_details.reasoning_tokens`). On the Responses surface the schema
goes in `text.format` (the Chat surface calls it `response_format` — do not mix them).

## 3. muse-spark-1.3 — tool-calling loop

Tool definition is **flat** (name/description/parameters at top level, not nested under
`function`); `tool_choice` only supports `"auto"`:

```python
tools = [{
    "type": "function", "name": "compute_variance",
    "description": "Compute variance between ordered qty a and received qty b.",
    "parameters": {"type": "object",
                   "properties": {"a": {"type": "number"}, "b": {"type": "number"}},
                   "required": ["a", "b"], "additionalProperties": False},
    "strict": True,
}]
resp = await client.responses.create(
    model=..., reasoning={"effort": "high"},
    include=["reasoning.encrypted_content"],   # required for stateless replay
    tools=tools, input="...call compute_variance with a=100 and b=87...")
```

Loop: items with `item.type == "function_call"` carry `item.name`, `item.arguments`
(a JSON **string** — `json.loads` it) and `item.call_id`. Execute in Python (the LLM
never does arithmetic), then send the next turn as **stateless replay**:

```python
resp = await client.responses.create(
    model=..., reasoning={"effort": "high"},
    include=["reasoning.encrypted_content"], tools=tools,
    input=[*(item.model_dump() for item in resp.output),          # reasoning + function_call
           {"type": "function_call_output", "call_id": item.call_id,
            "output": json.dumps(result)}],                        # result as JSON string
)
```

Until no `function_call` items remain; the last response's `output_text` is the answer.

**Gotcha (verified 400):** `include=["reasoning.encrypted_content"]` **cannot** be combined
with `previous_response_id` — the API rejects it with
`` `reasoning.encrypted_content` cannot be used with `previous_response_id` ``.
Use one or the other: `previous_response_id` (server-kept history, no `include`) **or**
stateless replay (replay `resp.output` + `function_call_output`, with `include`).
FourthMatch agent loops use stateless replay, per CLAUDE.md.

Verified: tool called with `{"a": 100, "b": 87}` → Python returned
`{"variance": 13.0, "variance_pct": 13.0}` → final text cited 13.0 / 13.0.

## 4. sam-3.1 — image segmentation (Responses, streamed, official parser)

Install: `pip install meta-sam-parser` (import `meta_sam_parser`, Python ≥3.10, zero deps).
Never parse the special-token text by hand.

Request: stream a Responses call with a **short noun phrase** + `input_image`
(base64 data URL works; hosted `image_url` also works):

```python
stream = await client.responses.create(
    model=os.environ["SEG_MODEL"],               # sam-3.1
    stream=True,
    input=[{"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": "cardboard box"},
        {"type": "input_image", "image_url": "data:image/png;base64,..."},
    ]}],
)
result = await parse_responses_stream(events, image_segmentation_format()).final_result()
```

Two cookbook details that are **required**, not optional (from
`meta-model-cookbook/07_sam/01_api_basics/python/sam_api.py`):
1. Adapt SDK events with `event.model_dump()` dicts, and **synthesize
   `response.output_text.done`** from `response.content_part.done` — the API does not send
   it and the parser needs it to close a lane.
2. Drain/claim `final_result()` while the stream context is still open
   (`async with stream, aclosing(events): ...`).

Result shape (`ImageSegmentationResult`): `.outcome.status == "completed"`,
`.records` (tuple), `.diagnostics`, `.media == "image"`, `.raw_output`.
Box records: `kind="box"`, `object_id` (str), `left/top/right/bottom` (floats, pixels in
source image, right/bottom half-open), `frame.frame_index`, `confidence` (None unless
`metadata={"include_confidence": "true"}`).
Mask records: `kind="mask"`, `mask.width/height/encoding/payload`, `bounds.left/top/right/bottom`;
decode with `decode_mask_to_raster(mask)` (bytes, one byte per pixel),
`decode_mask_to_rle`, `decode_mask_to_svg_path`. Raw wire format per frame line:
`<Nf><id><|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|><|mask;x=0;y=0;data=H,W,<enc>payload|>`
— grammar docs: dev.meta.ai/docs/sam/reading-segmentation.

Verified on `samples/cartoon.jpg` (the task text says `carton.jpg`; disk file is
`cartoon.jpg` and its bytes are **PNG despite the .jpg name** — send the real MIME type):
prompt `"cardboard box"` → **count=10**, 10 box + 10 mask records, e.g.
`object_id=2 left=140 top=542 right=531 bottom=861` (1448×1086 image).
Overlay (boxes + translucent masks, Pillow) saved to `samples/out/carton_overlay.png`
by the smoke script; `validate`: raise if `outcome.status != "completed"` or any
diagnostic has `severity == "error"`.

Optional request metadata: `{"mask_encoding": "one_bit"}` (compact) vs default
`"lossless"`, `{"include_confidence": "true"}` (values are strings).

## 5. sam-3.1 — video segmentation (Files API upload + streamed Responses)

Upload once, reuse the `file_id` everywhere (retries included):

```python
uploaded = await client.files.create(
    file=("dock.mp4", video_bytes, "video/mp4"), purpose="user_data")
file_id = uploaded.id          # "file-...", assert the prefix
stream = await client.responses.create(
    model=os.environ["SEG_MODEL"], stream=True,
    metadata={"mask_encoding": "one_bit"},
    input=[{"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": "cardboard box"},
        {"type": "input_video", "file_id": file_id}]}])
result = await parse_responses_stream(events, video_segmentation_format()).final_result()
```

Distinct tracks = unique `object_id` over all records with `frame.frame_index`
(an id names the same object on every frame; ids can be sparse per frame — count
unique ids, never records-per-line). Caps: 15,000 frames/request, 16 objects/frame,
billed per frame (minimum 50).

**Two performance gotchas that dominate everything else (both verified):**
1. **Buffer first, parse offline.** `meta_sam_parser` raster-decodes *every* mask to
   validate it (~0.2 s/mask, single-threaded Python). Parsing live inside the stream
   loop stalls socket reads until the server resets the connection
   (`ConnectionResetError` mid-stream, every attempt). The API itself is fast: draining
   the raw stream for the full 24 fps `dock.mp4` takes ~18 s (265 deltas, ~2.7 MB).
   Pattern used in the smoke script: `async for event in stream: events.append(event.model_dump())`,
   then replay the dicts through the cookbook `stream_events` adapter into
   `parse_responses_stream(...).final_result()`. Full-video offline parse: ~518 s.
2. **Downsample with ffmpeg for near-static scenes.** `ffmpeg -i dock.mp4 -vf fps=2 -an -c:v libx264 -pix_fmt yuv420p proxy.mp4`
   (265 → 22 frames, 4,502 → 374 records, parse ~41 s) returned the **identical
   10 distinct tracks** as 24 fps and 5 fps on this file (track spans scale exactly).
   Verified, not assumed — re-verify per scene before trusting a proxy in production;
   fast-moving objects may need a higher fps.

Verified on `samples/dock.mp4` (1280×720, 11.0 s, camera panning over cartons):
`distinct_tracks=10` — tracks 0,1,5,6,7,8 visible all 22 proxy frames, track 9 enters
at proxy frame 5, tracks 2/3/4 leave at frames 13/8/14 as the pan moves past them.

## 6. muse-voice-transcribe-1.0 — ASR (plain HTTP, NOT the SDK)

Never send audio to Spark. Endpoint: `POST https://api.meta.ai/v1/asr/transcribe`
(optional query `?sessionId=<id>`, echoed for log correlation), header
`Authorization: Bearer $MODEL_API_KEY`, `Accept: application/json` (buffered JSON;
`text/event-stream` also exists). Body is `multipart/form-data` with exactly two parts:

- `request` — JSON settings, part content-type `application/json`:
  `{"model": "muse-voice-transcribe-1.0", "audioEncoding": "WAV", "mode": "DIARIZATION"}`
  (`mode` also accepts e.g. `"PUSH_TO_TALK"`; optional `languageBias`, `keywords`.)
- `audio` — the file bytes, e.g. part filename `remark.wav`, content-type `audio/wav`.
  Max body 32 MB.

With httpx:

```python
r = await http.post(f"{BASE_URL}/asr/transcribe", params={"sessionId": "smoke-remark"},
    headers={"Authorization": f"Bearer {KEY}", "Accept": "application/json"},
    files={"request": (None, json.dumps(settings), "application/json"),
           "audio": ("remark.wav", wav_bytes, "audio/wav")})
```

Response JSON: `transcript` (full string) plus `turns` (list with `turnId`, `speaker`,
`startMs`, `endMs`, text). Verified on `samples/remark.wav` (16 kHz mono WAV):
`transcript == "Two boxes are damaged and the truck was late."`, 1 turn, ~3 s
(exact wording can vary slightly between runs — treat ASR text as fuzzy input).

## 7. muse-image-1.0 — image generation (synthetic test scenes only, never evidence)

```python
resp = await client.images.generate(
    model=os.environ["IMAGE_MODEL"],   # muse-image-1.0  (POST /v1/images/generations)
    prompt="warehouse receiving dock with 18 steel coils, CCTV angle", n=1)
item = resp.data[0]   # .b64_json (default response_format) or .url if response_format="url"
```

`size` is a `"WxH"` string; `n` is 1–10. **Gotcha:** the default `b64_json` payload on this
key decodes to **WEBP bytes** (1920×1280) regardless of your target filename — sniff/transcode
with Pillow before saving as `.png` (the smoke script does). Verified output
`samples/out/gen.png` (after transcode: genuine PNG, 1920×1280, CCTV-style dock with steel coils).
