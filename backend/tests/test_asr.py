"""ASR client (mock transport), wav conversion, remark upload + pipeline remark steps."""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.api.deps import get_delivery_service, get_pipeline_runner  # noqa: E402
from app.core.config import Settings  # noqa: E402
from app.core.errors import UpstreamModelError, ValidationError  # noqa: E402
from app.domain.schemas.config import ModelConfig  # noqa: E402
from app.domain.schemas.perception import PerceptionResult  # noqa: E402
from app.domain.schemas.remark import RemarkClaims, RemarkStatus, Transcription  # noqa: E402
from app.infra.audio import to_wav_16k_mono  # noqa: E402
from app.infra.cache import Sha256Cache  # noqa: E402
from app.infra.db.models import Delivery, Job, ModelCall, PoLine, PurchaseOrder, Vendor  # noqa: E402
from app.infra.db.session import Base, make_engine, make_session_factory  # noqa: E402
from app.infra.meta.asr import MetaTranscriber  # noqa: E402
from app.infra.storage import LocalFileStore  # noqa: E402
from app.main import create_app  # noqa: E402
from app.services.cases import CaseService  # noqa: E402
from app.services.deliveries import DeliveryService  # noqa: E402
from app.services.perception import PerceptionPipeline  # noqa: E402

CONFIG = ModelConfig(
    model_api_key="test-key", meta_base_url="https://asr.test/v1", perception_model="p", decision_model="d",
    compiler_model="c", bulk_model="b", seg_model="s", image_model="i", voice_model="voice-test",
)
OK_BODY = {"transcript": "Two boxes are damaged and the truck was late.",
           "turns": [{"turnId": "t1", "speaker": "S1", "startMs": 0, "endMs": 3000, "text": "Two boxes"}]}


def _factory(tmp_path: Path):  # noqa: ANN202
    tmp_path.mkdir(parents=True, exist_ok=True)
    engine = make_engine(tmp_path / "t.db")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def _transcriber(tmp_path: Path, handler: Any, **kw: Any) -> tuple[MetaTranscriber, Any]:
    factory = _factory(tmp_path)
    t = MetaTranscriber(CONFIG, session_factory=factory, transport=httpx.MockTransport(handler),
                        backoff_base_seconds=0.0, **kw)
    return t, factory


def test_asr_success_request_shape_and_model_call_row(tmp_path: Path) -> None:
    asyncio.run(_test_asr_success_request_shape_and_model_call_row(tmp_path))


async def _test_asr_success_request_shape_and_model_call_row(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return httpx.Response(200, json=OK_BODY)

    t, factory = _transcriber(tmp_path, handler)
    result = await t.transcribe(wav=b"RIFFfakewav", session_id="delivery-7")
    assert result.transcript == OK_BODY["transcript"]
    assert result.turns[0].start_ms == 0
    req = seen[0]
    assert req.url.path == "/v1/asr/transcribe" and req.url.params["sessionId"] == "delivery-7"
    assert req.headers["authorization"] == "Bearer test-key"
    assert req.headers["accept"] == "application/json"
    body = req.content
    assert b'name="request"' in body and b'name="audio"; filename="remark.wav"' in body
    assert b"Content-Type: application/json" in body and b"Content-Type: audio/wav" in body
    settings = json.loads(body.split(b'name="request"')[1].split(b"\r\n\r\n")[1].split(b"\r\n--")[0])
    assert settings == {"model": "voice-test", "audioEncoding": "WAV", "mode": "DIARIZATION"}
    session = factory()
    rows = session.query(ModelCall).all()
    assert len(rows) == 1
    assert (rows[0].model, rows[0].status, rows[0].cache_hit, rows[0].total_tokens) == ("voice-test", "ok", False, None)
    assert rows[0].latency_ms is not None
    session.close()


def test_asr_4xx_is_not_retried(tmp_path: Path) -> None:
    asyncio.run(_test_asr_4xx_is_not_retried(tmp_path))


async def _test_asr_4xx_is_not_retried(tmp_path: Path) -> None:
    calls = 0

    def handler(_req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": "bad audio"})

    t, factory = _transcriber(tmp_path, handler)
    with pytest.raises(UpstreamModelError) as exc:
        await t.transcribe(wav=b"x")
    assert calls == 1 and exc.value.code == "asr_rejected"
    session = factory()
    assert session.query(ModelCall).one().status == "error"
    session.close()


def test_asr_5xx_retries_then_succeeds_and_exhausts(tmp_path: Path) -> None:
    asyncio.run(_test_asr_5xx_retries_then_succeeds_and_exhausts(tmp_path))


async def _test_asr_5xx_retries_then_succeeds_and_exhausts(tmp_path: Path) -> None:
    calls = 0

    def flaky(_req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503) if calls < 3 else httpx.Response(200, json=OK_BODY)

    t, _ = _transcriber(tmp_path, flaky)
    assert (await t.transcribe(wav=b"x")).transcript
    assert calls == 3

    calls = 0

    def down(_req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    t2, _ = _transcriber(tmp_path / "b", down)
    with pytest.raises(UpstreamModelError) as exc:
        await t2.transcribe(wav=b"x")
    assert calls == 3 and exc.value.code == "model_upstream"


def test_asr_invalid_response_rejected_and_cache_hit(tmp_path: Path) -> None:
    asyncio.run(_test_asr_invalid_response_rejected_and_cache_hit(tmp_path))


async def _test_asr_invalid_response_rejected_and_cache_hit(tmp_path: Path) -> None:
    t, _ = _transcriber(tmp_path, lambda _r: httpx.Response(200, json={"nope": 1}))
    with pytest.raises(ValidationError):
        await t.transcribe(wav=b"x")

    calls = 0

    def handler(_req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=OK_BODY)

    factory = _factory(tmp_path / "c")
    cached = MetaTranscriber(CONFIG, session_factory=factory, cache=Sha256Cache(tmp_path / "cache"),
                             transport=httpx.MockTransport(handler))
    await cached.transcribe(wav=b"same")
    again = await cached.transcribe(wav=b"same")
    assert calls == 1 and again.transcript == OK_BODY["transcript"]
    session = factory()
    assert [r.cache_hit for r in session.query(ModelCall).order_by(ModelCall.id)] == [False, True]
    session.close()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
@pytest.mark.parametrize("suffix", ["wav", "m4a", "webm"])
def test_to_wav_16k_mono(tmp_path: Path, suffix: str) -> None:
    src = tmp_path / f"in.{suffix}"
    codec = {"wav": "pcm_s16le", "m4a": "aac", "webm": "libopus"}[suffix]
    gen = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-ac", "2", "-ar", "48000", "-c:a", codec, str(src)], capture_output=True)
    if gen.returncode != 0:
        pytest.skip(f"ffmpeg cannot encode {suffix}")
    dst = to_wav_16k_mono(src, tmp_path / "out" / "o.wav")
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=sample_rate,channels,codec_name",
         "-of", "json", str(dst)], capture_output=True, text=True, check=True).stdout)["streams"][0]
    assert (probe["sample_rate"], probe["channels"], probe["codec_name"]) == ("16000", 1, "pcm_s16le")


def test_to_wav_rejects_garbage(tmp_path: Path) -> None:
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg not installed")
    bad = tmp_path / "bad.webm"
    bad.write_bytes(b"not audio")
    with pytest.raises(ValidationError) as exc:
        to_wav_16k_mono(bad, tmp_path / "o.wav")
    assert exc.value.code == "remark_audio_invalid"


# ---------------------------------------------------------------- endpoint + pipeline
class FakeTranscriber:
    def __init__(self, text: str = OK_BODY["transcript"]) -> None:
        self.text = text
        self.calls: list[bytes] = []

    async def transcribe(self, *, wav: bytes, filename: str = "remark.wav",
                         session_id: str | None = None) -> Transcription:
        self.calls.append(wav)
        return Transcription(transcript=self.text)


class FakeClaimsModel:
    def __init__(self, claims: dict[str, Any]) -> None:
        self.claims = claims
        self.prompts: list[str] = []

    async def call_model(self, *, prompt: str, output_schema: type[Any], **_kw: Any) -> Any:
        self.prompts.append(prompt)
        return output_schema.model_validate(self.claims)


def _seed(factory: Any) -> tuple[int, int]:
    s = factory()
    vendor = Vendor(code="TST", name="Test Vendor", gstin="27FAKEX1234F1Z5", city="Pune", state="MH",
                    primary_category="cartons", contact_name="A", contact_email="a@example.com")
    s.add(vendor)
    s.flush()
    po = PurchaseOrder(po_number="FM/PO/26-27/998", vendor_id=vendor.id, order_date=date(2026, 10, 1),
                       expected_date=date(2026, 10, 8), status="open", total_paise=10000, synthetic=True)
    s.add(po)
    s.flush()
    line = PoLine(po_id=po.id, line_no=1, category="cartons", sku="BOX-1", description="Box", unit="box",
                  qty_ordered=10, unit_price_paise=1000, tolerance_pct=5.0, line_total_paise=10000)
    s.add(line)
    s.commit()
    ids = (po.id, line.id)
    s.close()
    return ids


def test_delivery_endpoint_stores_remark(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    po_id, _ = _seed(factory)
    service = DeliveryService(factory, LocalFileStore(tmp_path / "storage"))

    async def stub_runner(job_id: str, delivery_id: int) -> dict:
        return {}

    app = create_app()
    app.dependency_overrides[get_delivery_service] = lambda: service
    app.dependency_overrides[get_pipeline_runner] = lambda: stub_runner
    with TestClient(app) as client:
        resp = client.post("/api/deliveries", data={"po_id": po_id}, files={
            "video": ("dock.mp4", b"video", "video/mp4"),
            "remark": ("remark.webm", b"audio-bytes", "audio/webm")})
        assert resp.status_code == 201, resp.text
        plain = client.post("/api/deliveries", data={"po_id": po_id},
                            files={"video": ("dock.mp4", b"video", "video/mp4")})
        assert plain.status_code == 201
    s = factory()
    with_remark = s.get(Delivery, resp.json()["delivery_id"])
    without = s.get(Delivery, plain.json()["delivery_id"])
    assert with_remark is not None and with_remark.remark_audio_path
    assert Path(with_remark.remark_audio_path).read_bytes() == b"audio-bytes"
    assert without is not None and without.remark_audio_path is None
    queued = s.get(Job, resp.json()["job_id"])
    assert queued is not None and queued.events[0].payload["has_remark"] is True
    s.close()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_pipeline_remark_steps_persist_transcript_and_check(tmp_path: Path) -> None:
    asyncio.run(_test_pipeline_remark_steps_persist_transcript_and_check(tmp_path))


async def _test_pipeline_remark_steps_persist_transcript_and_check(tmp_path: Path) -> None:
    factory = _factory(tmp_path)
    po_id, line_id = _seed(factory)
    service = DeliveryService(factory, LocalFileStore(tmp_path / "storage"))
    wav = (ROOT / "samples" / "remark.wav").read_bytes()
    created = service.create_delivery(po_id=po_id, video_bytes=b"v", filename="d.mp4",
                                      remark_bytes=wav, remark_filename="remark.wav")
    s = factory()
    audio_path = s.get(Delivery, created.delivery_id).remark_audio_path  # type: ignore[union-attr]
    s.close()
    assert audio_path

    settings = Settings(model_api_key="k", perception_model="p", decision_model="d", compiler_model="c",
                        bulk_model="b", seg_model="s", image_model="i", voice_model="v",
                        storage_root=tmp_path / "storage")
    fake_t = FakeTranscriber()
    claims = {"claims": [{"kind": "damage", "category": "cartons", "quantity": 2, "text": "Two boxes are damaged"},
                         {"kind": "other", "category": None, "quantity": None, "text": "the truck was late"}]}
    model = FakeClaimsModel(claims)
    pipe = PerceptionPipeline(settings, factory, model_client=model, sam=object(),  # type: ignore[arg-type]
                              run_decision=False, transcriber=fake_t)
    text = await pipe._transcribe_remark(created.job_id, created.delivery_id, audio_path)
    assert text == OK_BODY["transcript"]
    assert fake_t.calls and fake_t.calls[0][:4] == b"RIFF"  # converted wav sent

    result = PerceptionResult(delivery_id=created.delivery_id, po_line_id=line_id, sam_run_id=1,
                              category="cartons", noun_phrase="box", observed_count=10, max_visible=10,
                              damaged_track_ids=[], evidence_quality="reliable")  # type: ignore[arg-type]
    s = factory()
    line = s.get(PoLine, line_id)
    s.close()
    assert line is not None
    await pipe._check_remark(created.job_id, created.delivery_id, text or "", [result], {str(line_id): line})
    assert "Remark transcript" in model.prompts[0]

    s = factory()
    delivery = s.get(Delivery, created.delivery_id)
    assert delivery is not None and delivery.remark_transcript == OK_BODY["transcript"]
    assert delivery.remark_check is not None and delivery.remark_check["status"] == "not_supported"
    events = [e.event_type for e in s.get(Job, created.job_id).events]  # type: ignore[union-attr]
    assert "transcribing_remark" in events and "transcribing_remark_finished" in events
    assert events.index("transcribing_remark") < events.index("remark_checked")
    # CaseDetail exposes it
    from app.infra.db.repositories.cases import SqlCaseRepository
    detail = CaseService(SqlCaseRepository(s)).get_case(po_id)
    assert detail.remark is not None and detail.remark.check is not None
    assert detail.remark.check.status is RemarkStatus.NOT_SUPPORTED
    s.close()


def test_remark_claims_schema_rejects_bad_kind() -> None:
    with pytest.raises(ValueError):
        RemarkClaims.model_validate({"claims": [{"kind": "mood", "text": "x"}]})
