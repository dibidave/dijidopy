#!/usr/bin/env python3
"""
Example script for logging in and fetching weight_log data via the dijible API.
Uses requests with a session to persist the auth cookie.
"""

import os
import requests
import pandas
import datetime
from typing import Optional

global BASE_URL, USERNAME, PASSWORD, VERIFY_SSL


def login(session: requests.Session) -> bool:
    """Log in and store the auth cookie in the session."""
    global BASE_URL, USERNAME, PASSWORD, VERIFY_SSL

    BASE_URL = os.environ.get("DIJIBLE_HOSTNAME")
    USERNAME = os.environ.get("DIJIBLE_USERNAME")
    PASSWORD = os.environ.get("DIJIBLE_PASSWORD")
    VERIFY_SSL = os.environ.get("DIJIBLE_VERIFY_SSL", "true").lower() == "true"

    resp = session.post(
        f"{BASE_URL}/login",
        json={"username": USERNAME, "password": PASSWORD},
        verify=VERIFY_SSL,
    )
    if resp.status_code == 200 and resp.json().get("ok"):
        return True
    print(f"Login failed: {resp.status_code} - {resp.text}")
    return False


def fetch_weight_logs(session: requests.Session, page: int = 1, limit: int = 100) -> dict:
    """Fetch weight logs with pagination."""
    resp = session.get(
        f"{BASE_URL}/api/weight",
        params={"page": page, "limit": limit},
        verify=VERIFY_SSL,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text}")
    return resp.json()


def get_weight_log(timedelta=None):

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    if not login(session):
        return 1

    data = []
    page = 1
    while True:
        result = fetch_weight_logs(session, page=page)
        data.extend(result["data"])
        if not result["pagination"].get("hasMore"):
            break
        page += 1

    df = pandas.DataFrame.from_records(data)

    # Rename weight_lbs to weight
    df.rename(columns={"weight_lbs": "weight"}, inplace=True)
    # Convert measured_at to datetime
    df["measured_at"] = pandas.to_datetime(df["measured_at"])
    # Convert logged_at to datetime
    df["logged_at"] = pandas.to_datetime(df["logged_at"])

    # Add a new column date which takes measured_at if it exists, otherwise logged_at
    df["date"] = df["measured_at"].fillna(df["logged_at"])
    # Convert date to datetime
    df["date"] = pandas.to_datetime(df["date"])

    # Drop the measured_at and logged_at columns
    df.drop(columns=["measured_at", "logged_at", "id"], inplace=True)

    now = datetime.datetime.now(datetime.timezone.utc)

    if timedelta:
        df = df[df["date"] > now - timedelta]

    # Make weight numeric
    df["weight"] = pandas.to_numeric(df["weight"])

    return df


def get_nutrient_id(session: requests.Session, nutrient_name: str) -> Optional[int]:
    """Get the nutrient id for the given nutrient name from the API."""
    resp = session.get(
        f"{BASE_URL}/api/consumption/nutrients",
        verify=VERIFY_SSL,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text}")
    data = resp.json().get("data", [])
    target = nutrient_name.lower()
    for n in data:
        if n.get("name", "").lower() == target:
            return n["id"]
    return None


def fetch_intakes(session: requests.Session, nutrient_ids: str, page: int = 1, limit: int = 100) -> dict:
    """Fetch intakes with nutrient values (calories, etc.) via pagination."""
    resp = session.get(
        f"{BASE_URL}/api/consumption/intakes",
        params={"page": page, "limit": limit, "nutrient_ids": nutrient_ids},
        verify=VERIFY_SSL,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text}")
    return resp.json()


def get_nutrient_log(nutrient_name: str, timedelta=None):
    """Fetch intake logs for the given nutrient. Returns a DataFrame with consumed_at and a column named after the nutrient (lowercase)."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})

    if not login(session):
        raise RuntimeError("Login failed")

    nutrient_id = get_nutrient_id(session, nutrient_name)
    if nutrient_id is None:
        raise RuntimeError(f"Nutrient '{nutrient_name}' not found in database")

    column_name = nutrient_name.lower()
    all_rows = []
    page = 1
    while True:
        result = fetch_intakes(session, str(nutrient_id), page=page)
        rows = result["data"]
        pagination = result["pagination"]

        for r in rows:
            consumed_at = r.get("consumed_at") or r.get("logged_at")
            nv = r.get("nutrient_values", {})
            value = nv.get(nutrient_id) or nv.get(str(nutrient_id))
            all_rows.append({
                "consumed_at": consumed_at,
                column_name: float(value) if value is not None else None,
            })

        if not pagination.get("hasMore"):
            break
        page += 1

    df = pandas.DataFrame(all_rows)
    df["consumed_at"] = [datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f%z") for date in df["consumed_at"]]
    df = df.sort_values("consumed_at").reset_index(drop=True)

    if timedelta:
        now = datetime.datetime.now(datetime.timezone.utc)
        df = df[df["consumed_at"] > now - timedelta]

    print(f"\nFetched {len(df)} intakes with {nutrient_name} values")
    return df


def get_calorie_log(timedelta=None):
    """Convenience wrapper for get_nutrient_log('calories')."""
    return get_nutrient_log("calories", timedelta=timedelta)


def get_caffeine_log(timedelta=None):
    """Convenience wrapper for get_nutrient_log('caffeine')."""
    return get_nutrient_log("caffeine", timedelta=timedelta)
