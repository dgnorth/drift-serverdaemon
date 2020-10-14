# -*- coding: utf-8 -*-
import datetime
import json
import logging
import os
import sys
import time
from logging import FileHandler

DAEMON_LOGS_FOLDER =  "c:/logs/drift-serverdaemon"
EVENT_LOG_FILENAME = "events.log"

args_tenant_name = None
args_ref = None
args_cmd = None


def get_script_name():
    return os.path.split(sys.argv[0])[-1]


logger = logging.getLogger(get_script_name())


def make_log_folder():
    log_folder = DAEMON_LOGS_FOLDER
    if os.path.exists(log_folder):
        return

    try:
        os.makedirs(log_folder)
    except:
        pass


def setup_logging(logname):
    make_log_folder()

    logger.setLevel(logging.INFO)

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s", datefmt="%Y.%m.%d %H:%M:%S")

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    log_folder = DAEMON_LOGS_FOLDER

    filename = "daemon_%s_%s.log" % (datetime.datetime.now().strftime("%Y-%m-%d"), logname)
    full_filename = os.path.join(log_folder, filename)
    handler = FileHandler(full_filename)
    handler.setLevel(logging.INFO)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logging.getLogger("requests").setLevel(logging.WARNING)


def log_event(event, description, details=None, severity="INFO", ref=None, tenant_name=None):
    make_log_folder()

    event_filename = os.path.join(DAEMON_LOGS_FOLDER, EVENT_LOG_FILENAME)
    row = {
        "event": event,
        "description": description,
        "details": details,
        "tenant_name": tenant_name or args_tenant_name,
        "ref": ref or args_ref,
        "cmd": args_cmd,
        "severity": severity,
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }

    events = []

    # try a few times in case the file is open by another process
    e = None
    for i in range(5):
        try:
            with open(event_filename, 'r') as f:
                events = json.load(f)
            break
        except Exception as e:
            time.sleep(0.2)

    events.append(row)

    # try a few times in case the file is open by another process
    e = None
    for i in range(5):
        try:
            with open(event_filename, 'w') as f:
                json.dump(events, f)
            break
        except Exception as e:
            time.sleep(0.2)
    else:
        logger.error("Could not save event (2) '%s': %s", event, e)
        return


def flush_events():
    event_filename = os.path.join(DAEMON_LOGS_FOLDER, EVENT_LOG_FILENAME)
    events = []
    try:
        with open(event_filename, 'r') as f:
            events = json.load(f)
    except Exception as e:
        return events

    with open(event_filename, 'w') as f:
        pass

    return events or []