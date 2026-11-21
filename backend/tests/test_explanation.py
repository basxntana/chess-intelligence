import json
import random
from types import SimpleNamespace

import anthropic
import chess
import pytest
from fastapi.testclient import TestClient

import app.explanation as explanation_module
from app.chess_core import Position
from app.chess_core.notation import san
from app.explanation import LLMUnavailable, build_facts, explain_move, validate
from app.explanation.grounding import allowed_tokens, check_sentence
from app.intelligence import analyze
from app.intelligence.benchmark import load
from app.main import app
from app.search import SearchConfig

FORK = "r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1"
CFG = SearchConfig(depth=3, candidates=3)


# ---------- SAN ----------
def test_san_matches_reference_library():
    rng = random.Random(5)
    for _ in range(60):
        pos, ref = Position(), chess.Board()
        for _ in range(rng.randint(1, 100)):
            moves = pos.legal_moves()
            if not moves:
                break
            m = rng.choice(moves)
            assert san(pos, m) == ref.san(chess.Move.from_uci(m.uci)), (pos.fen(), m.uci)
            pos.make(m)
            ref.push_uci(m.uci)


@pytest.mark.parametrize("fen,uci,expected", [
    ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1", "O-O"),
    ("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1c1", "O-O-O"),
    ("4k3/8/8/8/8/5N2/8/1N2K3 w - - 0 1", "b1d2", "Nbd2"),
    ("4k3/P7/8/8/8/8/8/4K3 w - - 0 1", "a7a8q", "a8=Q+"),
    ("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "a1a8", "Ra8#"),
    ("4k3/8/8/3pP3/8/8/8/4K3 w - d6 0 1", "e5d6", "exd6"),
])
def test_san_cases(fen, uci, expected):
    pos = Position(fen)
    assert san(pos, pos.parse_uci(uci)) == expected


# ---------- rule-based is always grounded ----------
def positions_for_grounding() -> list[str]:
    fens = [c["fen"] for c in load()["cases"]]
    rng = random.Random(9)
    while len(fens) < 60:
        pos = Position()
        for _ in range(rng.randint(4, 50)):
            moves = pos.legal_moves()
            if not moves:
                break
            pos.make(rng.choice(moves))
        if pos.legal_moves():
            fens.append(pos.fen())
    return fens


@pytest.mark.parametrize("fen", positions_for_grounding())
def test_rule_based_explanations_pass_grounding(fen):
    pos = Position(fen)
    a = analyze(pos, SearchConfig(depth=2, candidates=2))
    for cand in a["candidates"]:
        e = explain_move(pos, a, cand["move"])
        assert e["grounding"]["valid"], e["grounding"]["rejected"]
        assert e["san"].rstrip("+#") in e["summary"]["text"]
        assert e["source"] == "rule_based"


def test_rule_based_explains_fork_with_evidence():
    pos = Position(FORK)
    e = explain_move(pos, analyze(pos, CFG))
    assert e["san"] == "Nc7+"
    fork = [s for s in e["details"] if "fork" in s["text"]]
    assert fork and all(any(f["id"] == fid and f.get("motif") == "fork" for f in e["facts"]) for fid in fork[0]["facts"])


def test_explains_a_move_the_engine_did_not_choose():
    pos = Position("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1")
    a = analyze(pos, SearchConfig(depth=3, candidates=1), extra_moves=["a1a7"])
    e = explain_move(pos, a, "a1a7")
    assert e["san"] == "Ra7" and "candidate move" in e["summary"]["text"]
    assert any("Ra8#" in s["text"] and "better" in s["text"] for s in e["candidate_comparison"])
    with pytest.raises(ValueError):
        build_facts(pos, a, "g1h1")  # not analysed


# ---------- the validator rejects hallucinations ----------
@pytest.fixture(scope="module")
def fork_facts():
    pos = Position(FORK)
    return build_facts(pos, analyze(pos, CFG))


@pytest.mark.parametrize("text,cites,issue", [
    ("Nc7+ wins the rook.", [], "cites no facts"),
    ("Nc7+ is strong.", ["zz9"], "unknown facts"),
    ("Nc7+ prepares Qxh7.", ["move"], "names move Qxh7"),
    ("Nc7+ also eyes the h5 square.", ["move"], "names square h5"),
    ("Nc7+ is worth +3.10.", ["eval"], "number +3.10"),
    ("Nc7+ pins the rook.", ["move"], "mentions pin"),
    ("Nc7+ forks king and rook.", ["eval"], "mentions fork"),
    ("Nc7+ leads to mate in 3.", ["move"], "mate in 3"),
    ("Nc7+ leads to checkmate.", ["move"], "mentions mate"),
    ("Nc7+ guarantees victory.", ["move"], "guaranteed"),
    ("Nc7+ menyerang dengan garpu.", ["eval"], "mentions fork"),  # Indonesian motif word
    ("Nc7+ wins material.", ["eval"], "winning material"),
])
def test_validator_rejects(fork_facts, text, cites, issue):
    by_id = {f["id"]: f for f in fork_facts}
    issues = check_sentence({"text": text, "facts": cites}, by_id, allowed_tokens(fork_facts))
    assert any(issue in i for i in issues), issues


def test_validator_accepts_faithful_paraphrase(fork_facts):
    by_id = {f["id"]: f for f in fork_facts}
    fork_id = next(f["id"] for f in fork_facts if f.get("motif") == "fork")
    ok = {"text": "With Nc7+ the knight forks the king on e8 and the rook on a8, winning material.",
          "facts": ["move", fork_id]}
    assert check_sentence(ok, by_id, allowed_tokens(fork_facts)) == []


# ---------- LLM path (fake client: no network in tests) ----------
class FakeClient:
    def __init__(self, payload=None, stop_reason="end_turn", error=None):
        self.payload, self.stop_reason, self.error, self.calls = payload, stop_reason, error, []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        text = self.payload if isinstance(self.payload, str) else json.dumps(self.payload)
        return SimpleNamespace(stop_reason=self.stop_reason, stop_details=SimpleNamespace(category="cyber"),
                               content=[SimpleNamespace(type="text", text=text)], model="claude-opus-5-5",
                               usage=SimpleNamespace(input_tokens=900, output_tokens=200))


def llm_payload(facts, summary_text="Nc7+ is the engine's choice: the knight forks king and rook."):
    fork_id = next(f["id"] for f in facts if f.get("motif") == "fork")
    return {"summary": {"text": summary_text, "facts": ["move", "eval", fork_id]},
            "details": [{"text": "After Nc7+ the king must move and the rook on a8 falls.", "facts": ["move", fork_id]}],
            "tactical_warnings": [], "strategic_summary": [], "candidate_comparison": []}


@pytest.fixture(scope="module")
def fork_analysis():
    pos = Position(FORK)
    return pos, analyze(pos, CFG)


def test_llm_explanation_used_when_grounded(fork_analysis, fork_facts):
    pos, a = fork_analysis
    client = FakeClient(llm_payload(fork_facts))
    e = explain_move(pos, a, use_llm=True, language="English", client=client)
    assert e["source"] == "llm" and e["grounding"]["valid"] and e["model"] == "claude-opus-5-5"
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5" and call["fallbacks"] == "default"
    assert call["output_config"]["format"]["type"] == "json_schema"
    sent = json.loads(call["messages"][0]["content"].removeprefix("Facts:\n"))
    assert [f["id"] for f in sent] == [f["id"] for f in e["facts"]]


def test_llm_bad_sentence_dropped_but_rest_kept(fork_analysis, fork_facts):
    pos, a = fork_analysis
    payload = llm_payload(fork_facts)
    payload["details"].append({"text": "Later Qd8 seals the win.", "facts": ["move"]})
    payload["details"].append({"text": "The king is safe on e1.", "facts": ["move"]})
    e = explain_move(pos, a, use_llm=True, client=FakeClient(payload))
    assert e["source"] == "llm" and not e["grounding"]["valid"]
    assert [r["text"] for r in e["grounding"]["rejected"]] == ["Later Qd8 seals the win."]
    assert all("Qd8" not in s["text"] for s in e["details"])


@pytest.mark.parametrize("client,reason", [
    (FakeClient(stop_reason="refusal", payload="{}"), "refusal"),
    (FakeClient(stop_reason="max_tokens", payload="{"), "truncated"),
    (FakeClient(payload="not json"), "invalid JSON"),
    (FakeClient(error=anthropic.APIConnectionError(request=None)), "APIConnectionError"),
])
def test_llm_failures_fall_back_to_rule_based(fork_analysis, client, reason):
    pos, a = fork_analysis
    e = explain_move(pos, a, use_llm=True, client=client)
    assert e["source"] == "rule_based" and reason in e["grounding"]["fallback_reason"]
    assert e["summary"]["text"].startswith("Nc7+")


def test_llm_hallucinated_summary_falls_back(fork_analysis, fork_facts):
    pos, a = fork_analysis
    payload = llm_payload(fork_facts, summary_text="Qh5 wins the game by force.")
    e = explain_move(pos, a, use_llm=True, client=FakeClient(payload))
    assert e["source"] == "rule_based" and e["grounding"]["fallback_reason"] == "LLM output failed grounding"
    assert e["grounding"]["llm_rejected"]


def test_rule_based_validate_is_self_consistent(fork_facts):
    from app.explanation.rules import rule_based
    assert validate(rule_based(fork_facts), fork_facts)["valid"]


# ---------- API ----------
def test_api_explanation(monkeypatch):
    client = TestClient(app)
    r = client.post("/api/v1/analysis", json={"fen": FORK, "depth": 3}).json()
    assert r["result"]["explanation"]["san"] == "Nc7+" and r["result"]["explanation"]["source"] == "rule_based"
    url = f"/api/v1/analysis/{r['id']}/explain"

    e = client.post(url, json={"move": "d5b6"}).json()  # a move the engine did not rank
    assert e["move"] == "d5b6" and e["grounding"]["valid"]
    assert client.post(url, json={"move": "a1a8"}).status_code == 422
    assert client.post(url, json={"language": "x" * 99}).status_code == 422

    def unavailable(*_a, **_k):
        raise LLMUnavailable("no credentials")
    monkeypatch.setattr(explanation_module, "llm_explain", unavailable)
    e = client.post(url, json={"use_llm": True}).json()
    assert e["source"] == "rule_based" and "no credentials" in e["grounding"]["fallback_reason"]


def test_api_terminal_position_has_no_explanation():
    client = TestClient(app)
    r = client.post("/api/v1/analysis", json={"fen": "7k/6Q1/6K1/8/8/8/8/8 b - - 0 1"}).json()
    assert r["status"] == "done" and r["best_move"] is None and r["result"]["explanation"] is None
    assert client.post(f"/api/v1/analysis/{r['id']}/explain", json={}).status_code == 409


@pytest.mark.parametrize("text,ok", [
    ("Nc7+ scores +2.33.", True),       # sentence-final number is still checked
    ("Nc7+ scores -2.33.", False),      # wrong sign
    ("Nc7+ is 2.33 pawns better.", True),
    ("Nc7+ scores +2.90.", False),
])
def test_validator_numbers(fork_facts, text, ok):
    by_id = {f["id"]: f for f in fork_facts}
    issues = check_sentence({"text": text, "facts": ["move", "eval"]}, by_id, allowed_tokens(fork_facts))
    assert (not issues) == ok, issues


def test_real_sdk_without_credentials_falls_back(fork_analysis, monkeypatch, tmp_path):
    """No fake client: the real SDK with no key/profile must yield a rule-based answer, not a 500."""
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))  # no `ant auth login` profile either
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    pos, a = fork_analysis
    e = explain_move(pos, a, use_llm=True)
    assert e["source"] == "rule_based" and "credentials" in e["grounding"]["fallback_reason"]
