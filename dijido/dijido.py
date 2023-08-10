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
        username = os.environ["DIJIDO_USERNAME"]
    
    if "DIJIDO_PASSWORD" not in os.environ:
        password = getpass.getpass("Password:")
    else:
        password = os.environ["DIJIDO_PASSWORD"]
    
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

    URL_string = f"{os.environ['DIJIDO_HOSTNAME']}/{suffix}"

    if query_params:
        URL_string += "?"
        for key, value in query_params.items():
            URL_string += f"{key}={value}&"
        
        URL_string = URL_string[:-1]

    return URL_string


def get_logs(age=7):
    
    response = __SESSION__.get(
        endpoint(
            "logs",
            {
                "age": age
            }
        )
    )
    
    logs = response.json()["logs"]
    
    return logs


def get_datetime_from_date(date_string, inclusive=False):
    
    time = datetime.strptime(date_string, "%Y-%m-%d")
    time = time.replace(tzinfo=datetime.now().astimezone().tzinfo)
    
    if inclusive:
        one_day = timedelta(days=1)
        time = time + one_day
        
    return time


def get_time_now_aware():
    
    now = datetime.utcnow()
    now = now.replace(tzinfo=timezone.utc)
    
    return now


def convert_to_datetime(date_string):
    
    time = datetime.fromisoformat(date_string[0:-1])
    time = time.replace(tzinfo=timezone.utc)
    
    return time


def get_goals_by_name(name):
    
    global GOALS_BY_NAME
    
    if name in GOALS_BY_NAME:
        return GOALS_BY_NAME[name]
    
    response = __SESSION__.get(
        endpoint(
            "goals",
            {
                "name": name
            }
        )
    )
    
    goals = response.json()["goals"]
    
    if len(goals) > 1:
        warnings.warn(f"More than one goal with name {name} found")
    elif len(goals) == 0:
        return None
    
    GOALS_BY_NAME[name] = goals
    
    return goals


def get_goal_by_id(goal_id):
    
    global GOALS_BY_ID
    
    if goal_id in GOALS_BY_ID:
        return GOALS_BY_ID[goal_id].copy()
    
    response = __SESSION__.get(
        endpoint(
            "goals",
            {
                "_id": goal_id
            }
        )
    )
    
    goals = response.json()["goals"]
    
    if len(goals) > 1:
        warnings.warn(f"More than one goal with id {goal_id} found")
    elif len(goals) == 0:
        return None
    
    goal = goals[0]
    
    GOALS_BY_ID[goal_id] = goal
    
    return goal


def local_date_string(date):
    
    return date.astimezone(__LOCAL_TIMEZONE__).strftime("%Y-%m-%d %H:%M:%S")


def add_goal_durations_recursive(goal_sums, goal_id, goal_duration):
            
    goal = get_goal_by_id(goal_id)
    
    parent_goal_ids = goal["parent_goal_ids"]
    
    if goal_id not in goal_sums:
        goal_sums[goal_id] = 0

    goal_sums[goal_id] += goal_duration
    debug(f"Adding {goal_duration}s to {goal['name']}")
    
    if parent_goal_ids:
        
        for parent_goal_id in parent_goal_ids:
            add_goal_durations_recursive(goal_sums, parent_goal_id, goal_duration/len(parent_goal_ids))
            
            
def cap_and_clean_intervals(log_time_dict, start_time, end_time):
    
    times = sorted(log_time_dict.keys())
    
    # Seed an entry for the start and end times if they don't exist
    for time in [start_time, end_time]:
        if time not in log_time_dict:
            log_time_dict[time] = []
            
    for log_entry in log_time_dict[start_time]:
        
        # Ignore entries that are stopped right at the start time
        if log_entry["type"] == "Stopped":
            del log_time_dict[start_time][log_entry]
    
    for log_entry in log_time_dict[end_time]:
        
        # Ignore entries that are stopped right at the start time
        if log_entry["type"] == "Started":
            del log_time_dict[start_time][log_entry]
    
    active_goal_ids = {}
    
    for time in times:
        
        for log_entry in log_time_dict[time]:
            
            goal_id = log_entry["text"]
            
            if log_entry["type"] == "Started":
                if goal_id in active_goal_ids:
                    raise ValueError(f"Started goal_id {goal_id} at {time},"
                        " but is already going; this should be impossible")
                active_goal_ids[goal_id] = log_entry
            elif log_entry["type"] == "Stopped":
                
                if goal_id in active_goal_ids:
                    del active_goal_ids[goal_id]
                    continue
                    
                virtual_log_entry = log_entry.copy()
                virtual_log_entry["type"] = "Started"
                
                log_time_dict[start_time].append(virtual_log_entry)
    
    # Any gaols that are still around at the end get an automatic end cap
    for goal_id in active_goal_ids:
        
        if active_goal_ids[goal_id]["type"] == "Stopped":
            raise ValueError("There shouldn't be any stopped remaining after iterating the list of times")
        
        virtual_log_entry = active_goal_ids[goal_id].copy()
        virtual_log_entry["type"] = "Stopped"

        log_time_dict[end_time].append(virtual_log_entry)
        
            
def get_goal_times_by_date_range(start_date, end_date, split_overlapping=True):
    
    debug(f"Getting all goal times between {start_date} and {end_date}")
    
    # Get the date 
    start_time = get_datetime_from_date(start_date)
    end_time = get_datetime_from_date(end_date, inclusive=True)

    debug(f"Getting goal times between {start_time} and {end_time}")
    
    # Now we need to figure how many days in the past we need to go to make sure we capture all logs
    now = get_time_now_aware()
    days_since_start = (now - start_time).days + 2
    
    log_entries = get_logs(days_since_start)
    
    log_time_dict = {}

    for entry in log_entries:

        if entry["type"] not in ["Started", "Stopped"]:
            continue

        log_time = convert_to_datetime(entry["date"])
        
        # Skip any entries that happen before the start time or after the end time
        if log_time < start_time or log_time > end_time:
            continue

        if log_time not in log_time_dict:
            log_time_dict[log_time] = []

        log_time_dict[log_time].append(entry)

    debug(log_time_dict)
    
    # Make sure all intervals are complete(one start, one stop within the time ranges)
    cap_and_clean_intervals(log_time_dict, start_time, end_time)
    
    times = sorted(log_time_dict.keys())

    # We need to keep track of which goals are currently going
    active_goal_durations = {}
    goal_sums = { "Untracked": 0 }

    previous_time = start_time
    
    # Step through each time point in order
    for current_time in times:

        debug(local_date_string(current_time))
        
        goals_to_remove = set([])

        num_active_goals = len(active_goal_durations)

        debug(f"There are {num_active_goals} goals")
        
        interval_duration = (current_time - previous_time).total_seconds()
        
        if split_overlapping and num_active_goals:
            interval_duration /= num_active_goals

        # Increment the time allocated to each goal
        for goal_id in active_goal_durations:

            if interval_duration < 0:
                raise ValueError("This shouldn't happen anymore because we only keep entries that happen after our start time")

            # Weighted by number of goals
            active_goal_durations[goal_id] += interval_duration
            add_goal_durations_recursive(goal_sums, goal_id, interval_duration)

        # Loop through the log entries that happen at this time
        for log_entry in log_time_dict[current_time]:

            goal_id = log_entry["text"]

            if log_entry["type"] == "Started":
                debug(f"Adding {goal_id}")
                active_goal_durations[goal_id] = 0
            
            elif log_entry["type"] == "Stopped":
                del active_goal_durations[goal_id]

        debug(f"Between {previous_time} and {current_time}, we had {num_active_goals} active goals.")

        if num_active_goals == 0:
            
            goal_sums["Untracked"] += interval_duration
            
            debug(f"Adding {interval_duration}s to Untracked")

        previous_time = current_time
            
    goals = {}

    for goal_id, seconds in goal_sums.items():

        if goal_id == "Untracked":
            goal = {
                "name": "Untracked"
            }
        else:
            goal = get_goal_by_id(goal_id)

        goals[goal_id] = goal
        goals[goal_id]["duration"] = seconds
        
    return goals