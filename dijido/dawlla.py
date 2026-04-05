import requests
import getpass
import warnings
from datetime import datetime
from datetime import timezone
from datetime import timedelta
import os
import dotenv

__SESSION__ = None
__LOCAL_TIMEZONE__ = datetime.now().astimezone().tzinfo

DEBUG_MODE = False
GOALS_BY_ID = {}
GOALS_BY_NAME = {}

dotenv.load_dotenv()

def debug(message):
    
    if not DEBUG_MODE:
        return
    
    print(message)
    

def login(username=None, password=None):
    
    global __SESSION__
    __SESSION__ = requests.session()
    
    if not username:
        username = os.environ["DAWLLA_USERNAME"]
    
    if "DIJIDO_PASSWORD" not in os.environ:
        password = getpass.getpass("Password:")
    elif not password:
        password = os.environ["DAWLLA_PASSWORD"]
    
    response = __SESSION__.post(
        endpoint("login"),
        json={
            "username": username,
            "password": password
        }
    )

    
def endpoint(suffix, query_params=None):
    
    # Strip leading slash if exists
    suffix = suffix if suffix[0] != '/' else suffix[1:]

    URL_string = f"{os.environ['DAWLLA_HOSTNAME']}/{suffix}"

    if query_params:
        URL_string += "?"
        for key, value in query_params.items():
            URL_string += f"{key}={value}&"
        
        URL_string = URL_string[:-1]

    return URL_string


def get_accounts():
    
    response = __SESSION__.get(
        endpoint("accounts")
    )
    
    return response.json()["accounts"]


def get_categories():
    
    response = __SESSION__.get(
        endpoint("categories")
    )
    
    return response.json()["categories"]


def get_transactions():
    
    response = __SESSION__.get(
        endpoint("transactions")
    )
    
    return response.json()["transactions"]


def get_legal_entities():
    
    response = __SESSION__.get(
        endpoint("legal_entities")
    )
    
    return response.json()["legal_entities"]


def create_legal_entity(legal_entity):
    
    response = __SESSION__.post(
        endpoint("legal_entities"),
        json=legal_entity
    )
    
    return response.json()["legal_entity"]["_id"]