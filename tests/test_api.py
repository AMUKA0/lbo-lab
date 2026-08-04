"""API contract tests.

The engine is already covered; what these assert is the *transport* — that the
web client receives exactly what the engine computed, that impossible values
survive the trip as `null` rather than as invalid JSON or a fabricated number,
and that a structure the engine refuses to model arrives as a describable
finding rather than a 500.
"""

import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.presets import PRESETS, default_deal

client = TestClient(app)

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture
def deal() -> dict:
    return default_deal().model_dump()


def test_defaults_boot_the_client(deal):
    body = client.get("/api/defaults").json()
    assert body["assumptions"] == deal
    assert len(body["presets"]) == len(PRESETS)
    # The bands the sliders draw must be present, or the guardrails are invisible.
    assert {"entry_multiple", "total_leverage", "hold_years"} <= set(body["benchmarks"])


def test_run_returns_the_whole_model(deal):
    body = client.post("/api/run", json={"assumptions": deal}).json()

    assert len(body["years"]) == deal["hold_years"]
    # Per-tranche detail is carried through, not summarised into a total.
    assert [t["name"] for t in body["years"][0]["tranches"]] == body["tranche_names"]
    # The iterative interest solve actually ran and converged.
    assert all(1 < y["interest_iterations"] < 200 for y in body["years"])


def test_bridge_reconciles_exactly_over_the_wire(deal):
    """The identity the engine asserts must survive serialisation."""
    body = client.post("/api/run", json={"assumptions": deal}).json()
    bridge = body["bridge"]

    parts = (
        bridge["ebitda_growth"]
        + bridge["multiple_expansion"]
        + bridge["deleveraging"]
        + bridge["fee_drag"]
    )
    assert parts == pytest.approx(bridge["equity_gain"], abs=1e-6)
    assert bridge["reconciliation_error"] == pytest.approx(0.0, abs=1e-6)


def test_payload_is_strict_json_with_no_nan(deal):
    """NaN and inf are not JSON. A client that did `JSON.parse` on either would
    throw, so they must already be null on the way out."""
    deal["exit_fee_pct_ev"] = 0.0
    deal["tranches"][0]["cash_rate"] = 0.0
    deal["tranches"][1]["cash_rate"] = 0.0
    deal["revolver"]["cash_rate"] = 0.0

    raw = client.post("/api/run", json={"assumptions": deal}).text
    assert "NaN" not in raw and "Infinity" not in raw
    body = json.loads(raw)  # would raise on either

    # With no cash interest at all, coverage is mathematically infinite and is
    # reported as null rather than as a very large number.
    assert body["credit"][0]["interest_coverage"] is None


def test_failed_structure_is_a_finding_not_a_crash(deal):
    """Over-lever it until the revolver cannot fund the shortfall."""
    deal["tranches"][0]["leverage_turns"] = 8.0
    deal["tranches"][0]["cash_rate"] = 0.18
    deal["tranches"][0]["mandatory_amort_pct"] = 0.5
    deal["revolver"]["commitment"] = 0.0

    response = client.post("/api/run", json={"assumptions": deal})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["kind"] == "structure_failure"
    # The message has to say what to do about it, not just that it broke.
    assert "revolver" in detail["message"].lower()


def test_invalid_assumptions_are_rejected(deal):
    deal["entry_multiple"] = -1
    assert client.post("/api/run", json={"assumptions": deal}).status_code == 422


def test_sensitivity_grid_is_square_and_labelled(deal):
    body = client.post("/api/sensitivity", json={"assumptions": deal, "steps": 5}).json()
    assert len(body["entry_multiples"]) == 5
    assert len(body["exit_multiples"]) == 5
    assert len(body["values"]) == 5
    assert all(len(row) == 5 for row in body["values"])
    # Row-major, and IRR must rise across a row as the exit multiple rises.
    middle = body["values"][2]
    clean = [v for v in middle if v is not None]
    assert clean == sorted(clean)


def test_scenarios_report_survival_not_just_return(deal):
    body = client.post("/api/scenarios", json={"assumptions": deal}).json()
    names = [s["name"] for s in body["scenarios"]]
    assert names == ["Base", "Upside", "Downside", "Recession stress"]

    for scenario in body["scenarios"]:
        # Every case must say whether the structure held, even when it didn't.
        assert "failed" in scenario and "wiped_out" in scenario
        if scenario["failed"]:
            assert scenario["message"]
            assert scenario["irr"] is None


def test_exit_profile_covers_every_year_after_the_first(deal):
    body = client.post("/api/exit-profile", json={"assumptions": deal}).json()
    assert [y["exit_year"] for y in body["years"]] == list(range(2, deal["hold_years"] + 1))


def test_breakeven_solves_and_reports_unreachable(deal):
    body = client.post("/api/breakeven", json={"assumptions": deal, "target_irr": 0.2}).json()
    assert body["reachable"]
    assert body["expansion_required"] == pytest.approx(
        body["breakeven_exit_multiple"] - body["entry_multiple"]
    )

    absurd = client.post(
        "/api/breakeven", json={"assumptions": deal, "target_irr": 4.0}
    ).json()
    assert not absurd["reachable"]
    assert absurd["breakeven_exit_multiple"] is None


def test_schedule_exports_as_csv(deal):
    response = client.post("/api/schedule.csv", json={"assumptions": deal})
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.splitlines()[0].startswith("year,")


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p["name"])
def test_every_preset_is_runnable_or_fails_honestly(preset):
    """A preset must never 500. The 2007 vintage is *meant* to be punishing, so
    a 422 structure failure is an acceptable — and instructive — outcome."""
    response = client.post("/api/run", json={"assumptions": preset["assumptions"]})
    assert response.status_code in (200, 422)
    if response.status_code == 422:
        assert response.json()["detail"]["kind"] == "structure_failure"


def test_spa_fallback_never_serves_source_files():
    """The catch-all must return the app shell, not walk out of web/dist."""
    for path in ("/../pyproject.toml", "/..%2f..%2fapi/main.py", "/%2e%2e/README.md"):
        body = client.get(path).text
        assert "build-system" not in body
        assert "FastAPI" not in body


class TestWorkbookEndpoints:
    """The Excel round trip over HTTP. The engine-level tests prove the maths;
    these prove the transport does not lose or mangle it."""

    def _workbook(self, deal: dict) -> bytes:
        return client.post("/api/model.xlsx", json={"assumptions": deal}).content

    def test_a_deal_survives_the_round_trip_over_http(self, deal):
        payload = self._workbook(deal)
        assert payload[:2] == b"PK"  # a real xlsx is a zip

        response = client.post(
            "/api/import.xlsx",
            files={"file": ("model.xlsx", payload, _XLSX)},
        )
        assert response.status_code == 200
        assert response.json()["assumptions"] == deal

    def test_the_interest_cap_survives_the_round_trip(self, deal):
        """Non-default values on every switch, because equality on defaults
        would pass even if the cells were never written or never read."""
        deal["interest_limitation"] = {
            "enabled": True, "pct_of_ati": 0.50, "ati_basis": "ebitda",
        }
        response = client.post(
            "/api/import.xlsx",
            files={"file": ("model.xlsx", self._workbook(deal), _XLSX)},
        )
        assert response.status_code == 200
        assert response.json()["assumptions"]["interest_limitation"] == (
            deal["interest_limitation"])

    def test_a_covenant_break_still_reports_the_years_it_survived(self, deal):
        """Regression. Shortening the hold for a partial run has to trim EVERY
        per-year schedule, not just growth and margin — a covenant step-down
        left at full length makes the engine reject the shortened deal, and the
        caller is already inside an `except ValueError`, so the rejection is
        indistinguishable from failing in year one. This reported 0 survived
        years on a deal that serviced four of them."""
        from api.main import _replay
        from lbo_engine import Assumptions

        payload = dict(deal)
        payload["covenants"] = {
            "net_leverage_ceiling": [6.0, 5.5, 5.0, 4.5, 2.0],
            "interest_coverage_floor": None,
        }
        out = _replay(Assumptions.model_validate(payload))

        assert out["failed"] and out["failure_kind"] == "covenant"
        assert out["survived_years"] == 4
        assert out["breaks_in_year"] == 5
        assert out["partial_run"] is not None
        assert len(out["partial_run"].years) == 4

    def test_covenants_survive_the_round_trip(self, deal):
        """A step-down schedule, so a reader that collapsed it to one number
        would be caught."""
        deal["covenants"] = {
            "net_leverage_ceiling": [6.5, 6.0, 5.5, 5.0, 4.5],
            "interest_coverage_floor": 2.0,
        }
        response = client.post(
            "/api/import.xlsx",
            files={"file": ("model.xlsx", self._workbook(deal), _XLSX)},
        )
        assert response.status_code == 200
        assert response.json()["assumptions"]["covenants"] == deal["covenants"]

    def test_the_export_is_named_and_typed_for_excel(self, deal):
        response = client.post("/api/model.xlsx", json={"assumptions": deal})
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument")
        assert ".xlsx" in response.headers["content-disposition"]

    def test_a_recap_now_exports_rather_than_being_refused(self, deal):
        """This used to 422. The refusal claimed recaps were decisions made by
        search rather than by formula, which was only true of the PIK toggle —
        and even that is now exported as an overridable input."""
        deal["recaps"] = [{"year": 2, "amount": 50.0, "target_leverage_turns": None,
                           "tranche": None, "financing_fee_pct": 0.02}]
        response = client.post("/api/model.xlsx", json={"assumptions": deal})
        assert response.status_code == 200
        assert response.content[:2] == b"PK"

    def test_a_structure_that_breaks_says_so_rather_than_blaming_the_export(self, deal):
        """A deal with no complete schedule has nothing to export, and the
        reason is the deal, not the exporter."""
        # The same over-levering the structure-failure test uses.
        deal["tranches"][0]["leverage_turns"] = 8.0
        deal["tranches"][0]["cash_rate"] = 0.18
        deal["tranches"][0]["mandatory_amort_pct"] = 0.5
        deal["revolver"]["commitment"] = 0.0
        response = client.post("/api/model.xlsx", json={"assumptions": deal})
        assert response.status_code == 422
        assert "runs out of liquidity" in response.json()["detail"]["message"]

    def test_a_broken_workbook_comes_back_with_the_cells_to_fix(self, deal):
        import io as _io

        from openpyxl import load_workbook

        wb = load_workbook(_io.BytesIO(self._workbook(deal)))
        for name in ("Entry_Multiple", "Tax_Rate"):
            sheet, ref = next(iter(wb.defined_names[name].destinations))
            wb[sheet][ref.replace("$", "")] = None
        buf = _io.BytesIO(); wb.save(buf)

        response = client.post(
            "/api/import.xlsx", files={"file": ("broken.xlsx", buf.getvalue(), _XLSX)})
        assert response.status_code == 422
        problems = response.json()["detail"]["problems"]
        assert len(problems) >= 2
        assert all(p["cell"] for p in problems), "every problem must name its cell"

    def test_something_that_is_not_a_workbook_is_rejected_politely(self):
        response = client.post(
            "/api/import.xlsx", files={"file": ("cv.pdf", b"%PDF-1.4 not a workbook", _XLSX)})
        assert response.status_code == 422
        assert "could not be opened" in response.json()["detail"]["message"]


class TestCaseWorkbookEndpoint:
    """Downloading a case study as a live model — the strongest artefact here,
    and the one most likely to be forwarded to someone who never saw the site."""

    def test_every_column_downloads(self):
        from api.case_studies import CASES

        for case in CASES:
            for column in ("underwriting", "realised"):
                if getattr(case, column) is None:
                    continue
                r = client.get(f"/api/cases/{case.slug}/{column}.xlsx")
                assert r.status_code == 200, f"{case.slug}/{column}"
                assert r.content[:2] == b"PK"
                assert f"{case.slug}-{column}.xlsx" in r.headers["content-disposition"]

    def test_a_broken_column_downloads_rather_than_refusing(self):
        """RJR does not survive its hold. Refusing to export it would put the
        hole in the library exactly where the interesting deals are."""
        r = client.get("/api/cases/rjr-nabisco-kkr-1989/realised.xlsx")
        assert r.status_code == 200
        assert len(r.content) > 8_000

    def test_an_unknown_case_or_column_is_a_404_not_a_500(self):
        assert client.get("/api/cases/nope/underwriting.xlsx").status_code == 404
        assert client.get("/api/cases/rjr-nabisco-kkr-1989/wrong.xlsx").status_code == 404

    def test_the_route_does_not_shadow_the_case_detail_endpoint(self):
        """`/api/cases/{slug}/{column}.xlsx` and `/api/cases/{slug}` are easy to
        get into the wrong order in a router."""
        assert client.get("/api/cases/rjr-nabisco-kkr-1989").status_code == 200
