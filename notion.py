import requests
import pandas
import datetime

NOTION_INTEGRATION_TOKEN = None
WEIGHT_DATABASE_ID = "23aeb254c006488abc929c9aae706793"
INTAKE_DATABASE_ID = "fb30e296448d4f7f9ff7ec006e54bab3"
NOTION_API_ENDPOINT = "https://api.notion.com/v1/databases/{database_id}/query"

HEADERS = {
    "Authorization": NOTION_INTEGRATION_TOKEN,
    "Notion-Version": "2022-06-28"
}

def get_weight_log(timedelta=None):

    notion_data = []
    start_cursor = None

    while True:

        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        response = requests.post(
            NOTION_API_ENDPOINT.format(database_id=WEIGHT_DATABASE_ID),
            headers=HEADERS, json=payload
        )
        response = response.json()

        if "results" in response:
            notion_data.extend(response["results"])
        
        if not response.get("has_more"):
            break

        start_cursor = response.get("next_cursor")

    data = []

    for notion_datum in notion_data:

        date = notion_datum["properties"]["Measured At"]["formula"]["date"]["start"]
        # Convert date string to datetime object of the format
        # 2024-08-03T19:05:00.000+00:00

        date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f%z")

        data.append({
            "weight": notion_datum["properties"]["Weight"]["number"],
            "date": date
        })

    df = pandas.DataFrame(data)

    now = datetime.datetime.now(datetime.timezone.utc)

    if timedelta:
        df = df[df["date"] > now - timedelta]

    return df

def get_calorie_log(timedelta=None):

    notion_data = []
    start_cursor = None

    while True:

        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        response = requests.post(
            NOTION_API_ENDPOINT.format(database_id=INTAKE_DATABASE_ID),
            headers=HEADERS, json=payload
        )
        response = response.json()

        if "results" in response:
            notion_data.extend(response["results"])
        
        if not response.get("has_more"):
            break

        start_cursor = response.get("next_cursor")

    data = []

    for notion_datum in notion_data:

        date = notion_datum["properties"]["Consumed At"]["formula"]["date"]["start"]
        # Convert date string to datetime object of the format
        # 2024-08-03T19:05:00.000+00:00

        date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f%z")

        data.append({
            "calories": notion_datum["properties"]["Calories"]["formula"]["number"],
            "consumed_at": date
        })

    df = pandas.DataFrame(data)

    now = datetime.datetime.now(datetime.timezone.utc)

    if timedelta:
        df = df[df["date"] > now - timedelta]

    return df

def get_weight_log(timedelta=None):

    notion_data = []
    start_cursor = None

    while True:

        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        response = requests.post(
            NOTION_API_ENDPOINT.format(database_id=WEIGHT_DATABASE_ID),
            headers=HEADERS, json=payload
        )
        response = response.json()

        if "results" in response:
            notion_data.extend(response["results"])
        
        if not response.get("has_more"):
            break

        start_cursor = response.get("next_cursor")

    data = []

    for notion_datum in notion_data:

        date = notion_datum["properties"]["Measured At"]["formula"]["date"]["start"]
        # Convert date string to datetime object of the format
        # 2024-08-03T19:05:00.000+00:00

        date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f%z")

        data.append({
            "weight": notion_datum["properties"]["Weight"]["number"],
            "date": date
        })

    df = pandas.DataFrame(data)

    now = datetime.datetime.now(datetime.timezone.utc)

    if timedelta:
        df = df[df["date"] > now - timedelta]

    return df

def get_caffeine_log(timedelta=None):

    notion_data = []
    start_cursor = None

    while True:

        payload = {}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        response = requests.post(
            NOTION_API_ENDPOINT.format(database_id=INTAKE_DATABASE_ID),
            headers=HEADERS, json=payload
        )
        response = response.json()

        if "results" in response:
            notion_data.extend(response["results"])
        
        if not response.get("has_more"):
            break

        start_cursor = response.get("next_cursor")

    data = []

    for notion_datum in notion_data:

        date = notion_datum["properties"]["Consumed At"]["formula"]["date"]["start"]
        # Convert date string to datetime object of the format
        # 2024-08-03T19:05:00.000+00:00

        date = datetime.datetime.strptime(date, "%Y-%m-%dT%H:%M:%S.%f%z")

        data.append({
            "caffeine": notion_datum["properties"]["Caffeine (mg)"]["formula"]["number"],
            "consumed_at": date
        })

    df = pandas.DataFrame(data)

    now = datetime.datetime.now(datetime.timezone.utc)

    if timedelta:
        df = df[df["date"] > now - timedelta]

    return df