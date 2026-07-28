"""
Tests for the watsonx-hosted Granite embedding encoder and the encoder-identity
guard on the RAG index.

No test here makes a network call. The watsonx client is exercised against a
stubbed requests.post, and the identity guard is exercised through rag.py's own
module-level state.
"""
from __future__ import annotations

import json
import shutil

import numpy as np
import pytest

from src import rag
from src.watsonx_embedding import (
    RATE_LIMIT_RETRIES,
    EMBEDDING_DIM,
    MODEL_ID,
    WatsonxEmbedder,
    get_watsonx_embedder,
)


class _FakeResponse:
    def __init__(self, payload, status_code=200, headers=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def embedder():
    return WatsonxEmbedder(api_key="k", project_id="p", base_url="https://example.invalid")


class TestGetWatsonxEmbedder:
    def test_returns_none_without_credentials(self, monkeypatch):
        monkeypatch.delenv("WATSONX_API_KEY", raising=False)
        monkeypatch.delenv("WATSONX_PROJECT", raising=False)
        assert get_watsonx_embedder() is None

    def test_returns_none_with_key_but_no_project(self, monkeypatch):
        monkeypatch.setenv("WATSONX_API_KEY", "k")
        monkeypatch.delenv("WATSONX_PROJECT", raising=False)
        assert get_watsonx_embedder() is None

    def test_builds_encoder_when_configured(self, monkeypatch):
        monkeypatch.setenv("WATSONX_API_KEY", "k")
        monkeypatch.setenv("WATSONX_PROJECT", "p")
        enc = get_watsonx_embedder()
        assert enc is not None
        assert enc.encoder_id == f"watsonx:{MODEL_ID}"


class TestWatsonxEmbedderEncode:
    def test_encode_shapes_and_batches_and_preserves_order(self, embedder, monkeypatch):
        calls = []

        def fake_post(url, json=None, headers=None, timeout=None):
            calls.append(list(json["inputs"]))
            # Each vector encodes its own input index, so a reordering or a
            # misaligned batch boundary is detectable rather than invisible.
            return _FakeResponse({
                "results": [
                    {"embedding": [float(int(text.split()[1]))] * EMBEDDING_DIM}
                    for text in json["inputs"]
                ]
            })

        monkeypatch.setattr("src.watsonx_embedding.requests.post", fake_post)
        monkeypatch.setattr("src.watsonx_embedding._iam_token", lambda _k: "tok")

        out = embedder.encode([f"chunk {i}" for i in range(70)], batch_size=32)

        assert out.shape == (70, EMBEDDING_DIM)
        assert out.dtype == np.float32
        # 70 inputs at batch_size 32 must be exactly three requests, and every
        # input must appear exactly once, in order.
        assert [len(c) for c in calls] == [32, 32, 6]
        assert [t for c in calls for t in c] == [f"chunk {i}" for i in range(70)]
        # Row i must carry input i's marker value.
        assert [row[0] for row in out] == [float(i) for i in range(70)]

    def test_encode_caps_oversized_batch_size(self, embedder, monkeypatch):
        # rag.py builds with batch_size=64; the client must not forward that
        # straight to an endpoint it has only been exercised at 32.
        sizes = []

        def fake_post(url, json=None, headers=None, timeout=None):
            sizes.append(len(json["inputs"]))
            return _FakeResponse(
                {"results": [{"embedding": [0.1] * EMBEDDING_DIM} for _ in json["inputs"]]}
            )

        monkeypatch.setattr("src.watsonx_embedding.requests.post", fake_post)
        monkeypatch.setattr("src.watsonx_embedding._iam_token", lambda _k: "tok")
        embedder.encode([f"c{i}" for i in range(70)], batch_size=64)
        assert max(sizes) <= 32

    def test_encode_rejects_non_positive_batch_size(self, embedder):
        with pytest.raises(ValueError, match="batch_size must be positive"):
            embedder.encode(["a"], batch_size=0)

    def test_encode_raises_on_wrong_dimension(self, embedder, monkeypatch):
        # A well-formed response of the wrong width would otherwise build an
        # index in a vector space nothing else shares.
        monkeypatch.setattr(
            "src.watsonx_embedding.requests.post",
            lambda *a, **k: _FakeResponse({"results": [{"embedding": [0.1] * 512}]}),
        )
        monkeypatch.setattr("src.watsonx_embedding._iam_token", lambda _k: "tok")
        with pytest.raises(ValueError, match="expected 768"):
            embedder.encode(["a"])

    def test_encode_empty_returns_empty_matrix(self, embedder):
        out = embedder.encode([])
        assert out.shape == (0, EMBEDDING_DIM)

    def test_encode_accepts_a_bare_string(self, embedder, monkeypatch):
        monkeypatch.setattr(
            "src.watsonx_embedding.requests.post",
            lambda *a, **k: _FakeResponse({"results": [{"embedding": [0.2] * EMBEDDING_DIM}]}),
        )
        monkeypatch.setattr("src.watsonx_embedding._iam_token", lambda _k: "tok")
        assert embedder.encode("one string").shape == (1, EMBEDDING_DIM)

    def test_encode_raises_on_count_mismatch(self, embedder, monkeypatch):
        # A short result list would otherwise silently misalign every chunk with
        # the wrong vector.
        monkeypatch.setattr(
            "src.watsonx_embedding.requests.post",
            lambda *a, **k: _FakeResponse({"results": [{"embedding": [0.1] * EMBEDDING_DIM}]}),
        )
        monkeypatch.setattr("src.watsonx_embedding._iam_token", lambda _k: "tok")
        with pytest.raises(ValueError, match="1 embeddings for 2 inputs"):
            embedder.encode(["a", "b"])

    def test_encode_refreshes_token_once_on_401(self, embedder, monkeypatch):
        tokens = iter(["stale", "fresh"])
        seen = []

        def fake_post(url, json=None, headers=None, timeout=None):
            seen.append(headers["Authorization"])
            if len(seen) == 1:
                return _FakeResponse({}, status_code=401)
            return _FakeResponse({"results": [{"embedding": [0.3] * EMBEDDING_DIM}]})

        monkeypatch.setattr("src.watsonx_embedding.requests.post", fake_post)
        monkeypatch.setattr("src.watsonx_embedding._iam_token", lambda _k: next(tokens))

        out = embedder.encode(["a"])
        assert out.shape == (1, EMBEDDING_DIM)
        assert seen == ["Bearer stale", "Bearer fresh"]

    def test_retries_a_rate_limit_then_succeeds(self, embedder, monkeypatch):
        # Observed live: rebuilding 218 chunks is a burst of sequential calls and
        # watsonx answered 429. A transient limit must cost a wait, not the
        # Granite encoder for the rest of the process.
        slept = []
        responses = [
            _FakeResponse({}, status_code=429),
            _FakeResponse({"results": [{"embedding": [0.4] * EMBEDDING_DIM}]}),
        ]
        monkeypatch.setattr("src.watsonx_embedding.requests.post",
                            lambda *a, **k: responses.pop(0))
        monkeypatch.setattr("src.watsonx_embedding._iam_token", lambda _k: "tok")
        monkeypatch.setattr("src.watsonx_embedding.time.sleep", lambda s: slept.append(s))

        assert embedder.encode(["a"]).shape == (1, EMBEDDING_DIM)
        assert len(slept) == 1

    def test_retry_honours_retry_after_header(self, embedder, monkeypatch):
        slept = []
        responses = [
            _FakeResponse({}, status_code=429, headers={"Retry-After": "7"}),
            _FakeResponse({"results": [{"embedding": [0.4] * EMBEDDING_DIM}]}),
        ]
        monkeypatch.setattr("src.watsonx_embedding.requests.post",
                            lambda *a, **k: responses.pop(0))
        monkeypatch.setattr("src.watsonx_embedding._iam_token", lambda _k: "tok")
        monkeypatch.setattr("src.watsonx_embedding.time.sleep", lambda s: slept.append(s))

        embedder.encode(["a"])
        assert slept == [7.0]

    def test_gives_up_after_bounded_retries(self, embedder, monkeypatch):
        # Must not retry forever: a sustained outage has to surface so rag.py can
        # fall back rather than hang the request.
        calls = []

        def always_429(*a, **k):
            calls.append(1)
            return _FakeResponse({}, status_code=429)

        monkeypatch.setattr("src.watsonx_embedding.requests.post", always_429)
        monkeypatch.setattr("src.watsonx_embedding._iam_token", lambda _k: "tok")
        monkeypatch.setattr("src.watsonx_embedding.time.sleep", lambda s: None)

        with pytest.raises(RuntimeError):
            embedder.encode(["a"])
        assert len(calls) == 1 + RATE_LIMIT_RETRIES

    def test_does_not_retry_a_client_error(self, embedder, monkeypatch):
        # A 400 is a real fault; retrying it just wastes a judge's time.
        calls = []

        def bad_request(*a, **k):
            calls.append(1)
            return _FakeResponse({}, status_code=400)

        monkeypatch.setattr("src.watsonx_embedding.requests.post", bad_request)
        monkeypatch.setattr("src.watsonx_embedding._iam_token", lambda _k: "tok")
        with pytest.raises(RuntimeError):
            embedder.encode(["a"])
        assert len(calls) == 1

    def test_encode_propagates_http_error(self, embedder, monkeypatch):
        monkeypatch.setattr(
            "src.watsonx_embedding.requests.post",
            lambda *a, **k: _FakeResponse({}, status_code=500),
        )
        monkeypatch.setattr("src.watsonx_embedding._iam_token", lambda _k: "tok")
        with pytest.raises(RuntimeError):
            embedder.encode(["a"])


class TestEncoderIdentity:
    def test_encoder_id_reports_tfidf_when_no_encoder(self, monkeypatch):
        monkeypatch.setattr(rag, "_embedder", None)
        monkeypatch.setattr(rag, "_get_embedder", lambda: None)
        assert rag.encoder_id() == rag.TFIDF_ENCODER_ID

    def test_encoder_id_uses_encoder_attribute_when_present(self, monkeypatch):
        class _Enc:
            encoder_id = "watsonx:test-model"

        monkeypatch.setattr(rag, "_get_embedder", lambda: _Enc())
        assert rag.encoder_id() == "watsonx:test-model"

    def test_encoder_id_falls_back_to_sentence_transformers_name(self, monkeypatch):
        class _Plain:
            """A sentence-transformers model exposes no encoder_id attribute."""

        monkeypatch.setattr(rag, "_get_embedder", lambda: _Plain())
        assert rag.encoder_id() == f"sentence-transformers:{rag.EMBEDDING_MODEL}"

    def test_repo_ships_prebuilt_vectors_for_both_real_encoders(self):
        """Both environments must find vectors already built for them.

        The repo ships one vector file per encoder so neither a fresh clone nor
        the hosted deploy re-embeds the corpus on startup. If either file goes
        missing, that environment silently pays a full rebuild on its first
        citation, which on the hosted side is metered.
        """
        local = rag.embeddings_path_for(f"sentence-transformers:{rag.EMBEDDING_MODEL}")
        hosted = rag.embeddings_path_for(f"watsonx:{MODEL_ID}")
        assert local.exists(), f"missing prebuilt local vectors: {local.name}"
        assert hosted.exists(), f"missing prebuilt hosted vectors: {hosted.name}"

        chunks = json.loads(rag.CHUNKS_FILE.read_text())
        for path in (local, hosted):
            vecs = np.load(path)
            assert vecs.shape[0] == len(chunks), f"{path.name} rows != chunk count"
            assert vecs.shape[1] == EMBEDDING_DIM

    def test_the_two_encoders_share_a_dimension_but_not_a_vector_space(self):
        """Why identity tracking exists: a shape check cannot tell them apart.

        Both are 768-dimensional, so nothing about the array shape reveals a
        swap. The vectors themselves are different, which is exactly why the
        wrong file would produce confident nonsense rather than an error.
        """
        local = np.load(rag.embeddings_path_for(f"sentence-transformers:{rag.EMBEDDING_MODEL}"))
        hosted = np.load(rag.embeddings_path_for(f"watsonx:{MODEL_ID}"))
        assert local.shape == hosted.shape, "identical shapes are the whole problem"
        assert not np.allclose(local, hosted), "different encoders must give different vectors"


class TestCitationProvenanceIsExposed:
    """A judge must be able to read which encoder served a citation, not infer it."""

    def test_judges_reports_active_and_index_encoders(self):
        from fastapi.testclient import TestClient
        from src.app import app

        body = TestClient(app).get("/judges").json()
        prov = body["citation_provenance"]
        assert prov["active"], "the active encoder must be named"
        assert prov["index_built_with"] == json.loads(rag.INDEX_META_FILE.read_text())["encoder"]

    def test_provenance_never_breaks_the_judges_page(self, monkeypatch):
        # The transparency page must survive its own transparency field failing.
        import src.app as app_module

        monkeypatch.setattr(
            rag, "encoder_id", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        out = app_module._citation_provenance()
        assert out["active"] is None
        assert "boom" in out["error"]


class TestEncoderFailureIsSurvivable:
    """
    A hosted encoder can fail mid-run. That must degrade the citation, never
    take down the conformance check that asked for it.
    """

    @pytest.fixture(autouse=True)
    def _reset(self, monkeypatch, tmp_path):
        # Point the module at a throwaway index. Without this, resolving a
        # different encoder here rebuilds the COMMITTED index in place and
        # dirties the working tree (observed: embeddings.npy rewritten at
        # 218x512 by the deterministic encoder).
        shutil.copytree(rag.INDEX_DIR, tmp_path / "index")
        monkeypatch.setattr(rag, "INDEX_DIR", tmp_path / "index")
        monkeypatch.setattr(rag, "CHUNKS_FILE", tmp_path / "index" / "chunks.json")
        monkeypatch.setattr(rag, "EMBEDDINGS_FILE", tmp_path / "index" / "embeddings.npy")
        monkeypatch.setattr(rag, "INDEX_META_FILE", tmp_path / "index" / "index_meta.json")
        monkeypatch.setattr(rag, "_chunks", None)
        monkeypatch.setattr(rag, "_embeddings", None)
        monkeypatch.setattr(rag, "_encoder_failed", False)
        monkeypatch.setattr(rag, "_embedder", None)
        yield
        rag._chunks = None
        rag._embeddings = None

    def test_query_encode_failure_returns_a_citation_instead_of_raising(self, monkeypatch):
        class _Exploding:
            encoder_id = "watsonx:boom"

            def encode(self, *a, **k):
                raise RuntimeError("watsonx 503")

        monkeypatch.setattr(rag, "_get_embedder", lambda: _Exploding())
        # Must not raise. engine.py calls this per finding; an exception here
        # would 500 the entire check.
        out = rag.retrieve_citation("DCMP-CAP-01", "caption line length")
        assert isinstance(out, str) and out

    def test_demote_is_sticky_and_flips_reported_identity(self, monkeypatch):
        class _Enc:
            encoder_id = "watsonx:boom"

        monkeypatch.setattr(rag, "_get_embedder", lambda: _Enc())
        assert rag.encoder_id() == "watsonx:boom"

        # Restore the real resolver so the sticky flag is what decides.
        monkeypatch.undo()
        monkeypatch.setattr(rag, "_encoder_failed", False)
        monkeypatch.setattr(rag, "_embedder", None)
        rag._demote_encoder("simulated failure")
        assert rag._encoder_failed is True
        assert rag._get_embedder() is None
        # This is what stops the rebuild-every-load loop: after demotion the
        # reported identity matches what a fallback build actually wrote.
        assert rag.encoder_id() == rag.TFIDF_ENCODER_ID

    def test_no_network_call_when_watsonx_is_unconfigured(self, monkeypatch):
        """The offline path must stay offline: no credentials, no requests."""
        monkeypatch.delenv("WATSONX_API_KEY", raising=False)
        monkeypatch.delenv("WATSONX_PROJECT", raising=False)

        calls = []
        monkeypatch.setattr(
            "src.watsonx_embedding.requests.post",
            lambda *a, **k: calls.append(a) or _FakeResponse({"results": []}),
        )
        assert get_watsonx_embedder() is None
        assert calls == []


class TestQuotaGuardOnColdStart:
    """A hosted encoder must never re-embed the corpus at runtime.

    Re-embedding 218 chunks costs ~22k tokens. The hosted filesystem is
    ephemeral, so the mismatch branch runs on every cold start (~20/day), which
    is ~436k tokens/day against a 300k/month plan. That is exactly how the
    quota was drained, taking the vision, Guardian and summary calls down with
    it, since they share the same allowance.
    """

    @pytest.fixture(autouse=True)
    def _isolated_index(self, monkeypatch, tmp_path):
        shutil.copytree(rag.INDEX_DIR, tmp_path / "index")
        monkeypatch.setattr(rag, "INDEX_DIR", tmp_path / "index")
        monkeypatch.setattr(rag, "CHUNKS_FILE", tmp_path / "index" / "chunks.json")
        monkeypatch.setattr(rag, "EMBEDDINGS_FILE", tmp_path / "index" / "embeddings.npy")
        monkeypatch.setattr(rag, "INDEX_META_FILE", tmp_path / "index" / "index_meta.json")
        monkeypatch.setattr(rag, "_chunks", None)
        monkeypatch.setattr(rag, "_embeddings", None)
        monkeypatch.setattr(rag, "_encoder_failed", False)
        monkeypatch.setattr(rag, "_embedder", None)
        yield
        rag._chunks = None
        rag._embeddings = None

    def test_metered_encoder_is_recognised(self):
        assert rag._is_metered(f"watsonx:{MODEL_ID}") is True
        assert rag._is_metered(rag.TFIDF_ENCODER_ID) is False
        assert rag._is_metered(f"sentence-transformers:{rag.EMBEDDING_MODEL}") is False

    def test_hosted_reindex_is_off_by_default(self, monkeypatch):
        monkeypatch.delenv("ACCESSGATE_ALLOW_HOSTED_REINDEX", raising=False)
        assert rag._hosted_reindex_allowed() is False

    def test_cold_start_mismatch_does_not_call_the_hosted_encoder(self, monkeypatch):
        monkeypatch.delenv("ACCESSGATE_ALLOW_HOSTED_REINDEX", raising=False)

        calls = []

        class _Metered:
            encoder_id = f"watsonx:{MODEL_ID}"

            def encode(self, texts, **kw):
                calls.append(len(list(texts)))
                raise AssertionError("hosted encoder must not re-embed the corpus")

        # Mirror the real resolver: it returns None once the encoder has been
        # demoted. Patching _get_embedder to unconditionally hand back the
        # metered encoder would bypass the very check under test.
        def _resolve():
            return None if rag._encoder_failed else _Metered()

        monkeypatch.setattr(rag, "_get_embedder", _resolve)
        # Remove the prebuilt hosted vectors so the guard path is what runs.
        # With them present the fast path loads them and never re-embeds, which
        # is the normal case; this test covers the fallback where they are
        # absent and a naive implementation would re-embed through the meter.
        rag.embeddings_path_for(f"watsonx:{MODEL_ID}").unlink(missing_ok=True)
        # And make the stored identity genuinely differ from the active one.
        # index_meta.json records whichever build ran last, so do not depend on
        # what happens to be committed; state the mismatch this test is about.
        rag.INDEX_META_FILE.write_text(json.dumps(
            {"encoder": f"sentence-transformers:{rag.EMBEDDING_MODEL}", "dim": EMBEDDING_DIM}))
        rag._load_index()

        assert calls == [], "the corpus was re-embedded against a metered encoder"
        assert rag._read_index_meta()["encoder"] == rag.TFIDF_ENCODER_ID

    def test_opt_in_still_permits_a_deliberate_offline_build(self, monkeypatch):
        monkeypatch.setenv("ACCESSGATE_ALLOW_HOSTED_REINDEX", "1")
        assert rag._hosted_reindex_allowed() is True
