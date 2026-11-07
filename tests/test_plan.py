from mti.config import AUTOMOTIVE_CODES, MIRROR_PARTNERS, MOROCCO, build_request_plan


def test_plan_size_per_year():
    plan = build_request_plan([2023])
    # 1 chapters call + 2 flows x (1 partner total + 3 automotive headings) + 1 mirror call
    assert len(plan) == 1 + 2 * (1 + len(AUTOMOTIVE_CODES)) + 1


def test_request_ids_are_unique():
    plan = build_request_plan([2021, 2022, 2023])
    ids = [request.request_id for request in plan]
    assert len(ids) == len(set(ids))


def test_params_request_totals_only():
    request = build_request_plan([2023])[0]
    params = request.params()
    assert params["partner2Code"] == "0"
    assert params["customsCode"] == "C00"
    assert params["motCode"] == "0"
    assert params["period"] == "2023"


def test_all_partners_requests_omit_partner_code():
    plan = build_request_plan([2023])
    partners_total = [r for r in plan if r.dataset == "partners_total"]
    assert partners_total and all("partnerCode" not in r.params() for r in partners_total)


def test_mirror_request_targets_morocco_as_partner():
    mirror = [r for r in build_request_plan([2023]) if r.dataset == "mirror_partners"][0]
    assert mirror.params()["partnerCode"] == str(MOROCCO)
    assert mirror.reporters == set(MIRROR_PARTNERS)
