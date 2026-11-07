PROFILE = {
    "date_column": "Posted",
    "description_column": "Merchant",
    "amount_column": "Charge",
    "date_format": "%m/%d/%Y",
    "positive_is": "refund",
}


def upload(client, account, data, name="statement.csv", period="2025-10"):
    response = client.post(
        "/api/imports",
        data={"account_id": account, "period": period},
        files={"file": (name, data)},
    )
    assert response.status_code == 201, response.text
    return response.json()


def apply(client, job, mapping=PROFILE):
    response = client.put("/api/imports/" + job["id"] + "/mapping", json=mapping)
    assert response.status_code == 200, response.text
    return response.json()


def test_mapping_remembers_all_fields_and_auto_applies_to_new_file(client, account_id):
    first = upload(
        client, account_id, b"Posted,Merchant,Charge\n10/02/2025,Panera,-12.50\n"
    )
    assert first["status"] == "prepared"
    apply(client, first)
    account = next(
        a for a in client.get("/api/accounts").json() if a["id"] == account_id
    )
    assert account["csv_mapping"] == PROFILE
    second = upload(
        client,
        account_id,
        b"Posted,Merchant,Charge\n11/03/2025,Panera,-20.00\n",
        period="2025-11",
    )
    assert second["status"] == "review" and second["source"]["mapping"] == PROFILE
    assert second["rows"][0]["date"] == "2025-11-03"
    assert second["rows"][0]["description"] == "Panera"
    assert (
        second["rows"][0]["amount"] == 2000 and second["rows"][0]["kind"] == "purchase"
    )
    assert client.get("/api/transactions").json() == []


def test_existing_queued_file_can_use_mapping_learned_after_upload(client, account_id):
    first = upload(
        client, account_id, b"Posted,Merchant,Charge\n10/02/2025,Panera,-12.50\n"
    )
    queued = upload(
        client,
        account_id,
        b"Posted,Merchant,Charge\n11/03/2025,Panera,-20.00\n",
        period="2025-11",
    )
    assert queued["source"]["mapping"] is None
    apply(client, first)
    response = client.post("/api/imports/" + queued["id"] + "/mapping/default")
    assert response.status_code == 200
    result = response.json()
    assert result["source"]["mapping"] == PROFILE and result["status"] == "review"
    assert result["rows"][0]["date"] == "2025-11-03"
    assert result["rows"][0]["description"] == "Panera"


def test_profiles_are_per_card_and_rename_preserves_them(client, account_id):
    second_card = client.post("/api/accounts", json={"name": "Second card"}).json()[
        "id"
    ]
    first = upload(
        client, account_id, b"Posted,Merchant,Charge\n10/02/2025,Panera,-12.50\n"
    )
    apply(client, first)
    other = upload(
        client, second_card, b"Date,Description,Amount\n2025-11-03,Grocer,10.00\n"
    )
    assert other["status"] == "prepared" and other["source"]["mapping"] is None
    alternate = {
        "date_column": "Date",
        "description_column": "Description",
        "amount_column": "Amount",
        "date_format": "%Y-%m-%d",
        "positive_is": None,
    }
    apply(client, other, alternate)
    client.put("/api/accounts/" + account_id, json={"name": "Renamed"})
    accounts = {a["id"]: a for a in client.get("/api/accounts").json()}
    assert accounts[account_id]["csv_mapping"] == PROFILE
    assert accounts[second_card]["csv_mapping"] == alternate


def test_missing_headers_fall_back_to_mapping_without_overwriting_card_profile(
    client, account_id
):
    apply(
        client,
        upload(
            client, account_id, b"Posted,Merchant,Charge\n10/02/2025,Panera,-12.50\n"
        ),
    )
    changed = upload(
        client, account_id, b"Posted,Payee,Charge\n11/03/2025,Panera,-20.00\n"
    )
    assert changed["status"] == "prepared" and changed["rows"] == []
    assert changed["source"]["mapping"] is None and changed["source"]["mapping_warning"]
    account = next(
        a for a in client.get("/api/accounts").json() if a["id"] == account_id
    )
    assert account["csv_mapping"] == PROFILE
    corrected = apply(client, changed, {**PROFILE, "description_column": "Payee"})
    assert not corrected["source"]["mapping_warning"]
    assert (
        next(a for a in client.get("/api/accounts").json() if a["id"] == account_id)[
            "csv_mapping"
        ]["description_column"]
        == "Payee"
    )


def test_saved_mapping_never_replaces_existing_review_edits(client, account_id):
    first = apply(
        client,
        upload(
            client, account_id, b"Posted,Merchant,Charge\n10/02/2025,Panera,-12.50\n"
        ),
    )
    row = {
        **first["rows"][0],
        "source_index": 0,
        "description": "Manually corrected",
        "selected": False,
    }
    client.put("/api/imports/" + first["id"] + "/review", json={"rows": [row]})
    second = upload(
        client, account_id, b"Posted,Merchant,Charge\n11/03/2025,Grocer,-20.00\n"
    )
    apply(client, second, {**PROFILE, "positive_is": None})
    result = client.post("/api/imports/" + first["id"] + "/mapping/default").json()
    assert result["rows"][0]["description"] == "Manually corrected"
    assert result["rows"][0]["selected"] is False
    assert result["source"]["mapping"] == PROFILE


def test_committed_mapping_is_retained_and_default_route_cannot_remap_it(
    client, account_id, category_id
):
    job = apply(
        client,
        upload(
            client, account_id, b"Posted,Merchant,Charge\n10/02/2025,Panera,-12.50\n"
        ),
    )
    row = {**job["rows"][0], "source_index": 0, "category_id": category_id}
    client.put("/api/imports/" + job["id"] + "/review", json={"rows": [row]})
    saved = client.post("/api/imports/" + job["id"] + "/commit").json()
    assert saved["status"] == "committed" and saved["source"]["mapping"] == PROFILE
    result = client.post("/api/imports/" + job["id"] + "/mapping/default").json()
    assert result["status"] == "committed" and result["source"]["mapping"] == PROFILE
    assert len(client.get("/api/transactions").json()) == 1


def test_invalid_mapping_does_not_save_card_default(client, account_id):
    job = upload(
        client, account_id, b"Posted,Merchant,Charge\n10/02/2025,Panera,-12.50\n"
    )
    response = client.put(
        "/api/imports/" + job["id"] + "/mapping",
        json={**PROFILE, "description_column": "Missing"},
    )
    assert response.status_code == 422
    assert (
        next(a for a in client.get("/api/accounts").json() if a["id"] == account_id)[
            "csv_mapping"
        ]
        is None
    )
    assert client.post("/api/imports/missing/mapping/default").status_code == 404
