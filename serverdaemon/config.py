# -*- coding: utf-8 -*-
import json
import os
import os.path
import random
import socket
# Get basic info from per-tier config file
from serverdaemon.utils import get_tier_name, get_tags, get_repository, get_api_key, get_region
from serverdaemon.utils import get_battledaemon_credentials, get_battleserver_credentials
TIER = get_tier_name()

head, tail = os.path.split(__file__)
config_filename = os.path.join(head, "../config/config.json")

with open(config_filename) as f:
    config_file = json.load(f)

# Battleserver Daemon specific config values:
STORAGE_DRIVE = config_file.get("storage-drive", "T")
# Folder to store downloaded zip files (temporarily).
BSD_TEMP_FOLDER = STORAGE_DRIVE + ":/temp"
# Folder to store battleserver build images
BSD_BATTLESERVER_FOLDER = STORAGE_DRIVE + ":/builds"
# Folder to store battleserver log files
BSD_LOGS_FOLDER =  STORAGE_DRIVE + ":/logs/battleserver"
# Serverdaemon log folder
DAEMON_LOGS_FOLDER =  STORAGE_DRIVE + ":/logs/drift-serverdaemon"

tags = get_tags()
product_name = tags.get("drift-product_name")
group_name = tags.get("drift-group_name")
api_key = get_api_key()
region_name = get_region() or config_file.get("default_region")

battledaemon_credentials = get_battledaemon_credentials()
battleserver_credentials = get_battleserver_credentials()

BUILD_BUCKET, BUILD_PATH, S3_REGION_NAME = get_repository()
