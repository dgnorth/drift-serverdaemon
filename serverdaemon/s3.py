# -*- coding: utf-8 -*-
"""
    Drift game server management - S3 Functionality
    ------------------------------------------------
"""
import datetime
import json
import os
import os.path
import sys
import time

import dateutil.parser as parser
from boto.s3 import connect_to_region
from boto.s3.connection import OrdinaryCallingFormat

import config
from serverdaemon.logsetup import logger

# This is the S3 bucket name for server builds:
bucket_name = "ncl-teamcity"

def sync_index():
    path = config.BUILD_PATH
    bucket_name = config.BUILD_BUCKET
    file_path = "{path}/index.json".format(path=path)
    folder = "config/{path}/".format(path=path)

    logger.info("Downloading index.json for %s in %s to %s...", file_path, bucket_name, folder)
    try:
        conn = connect_to_region(config.S3_REGION_NAME, calling_format=OrdinaryCallingFormat())
    except Exception as e:
        logger.exception("Fatal error! Could not connect to S3 region '%s': %s", config.S3_REGION_NAME, e)
        sys.exit(2)
    bucket = conn.get_bucket(bucket_name)
    key = bucket.get_key(file_path)
    if key is None:
        logger.error("Index file '%s' not found on S3" % file_path)
        sys.exit(1)
    contents = key.get_contents_as_string()
    try:
        os.makedirs(folder)
    except:
        pass
    local_filename = os.path.join(folder, "index.json")
    with open(local_filename, "wb") as f:
        f.write(contents)

    d = json.loads(contents)
    for entry in d["refs"]:
        path = entry["build_manifest"]
        key = bucket.get_key(path)
        if key is None:
            logger.error("File '%s' not found on S3" % path)
            sys.exit(1)
        contents = key.get_contents_as_string()
        local_filename = os.path.join(folder, path.split("/")[-1])
        with open(local_filename, "wb") as f:
            f.write(contents)

def get_manifest(ref):
    index_file = get_index()
    try:
        refitem = [refitem for refitem in index_file["refs"] if refitem["ref"] == ref and refitem["target_platform"] == "WindowsServer"][0]
    except IndexError:
        logger.warning("Ref '%s' not found in index file", ref)
        return None
    path = refitem["build_manifest"]
    folder = "config/{repo}/".format(repo=config.BUILD_PATH)
    local_filename = os.path.join(folder, path.split("/")[-1])
    cnt = 0
    while 1:
        try:
            with open(local_filename, "r") as f:
                manifest = json.load(f)
                break
        except Exception as e:
            cnt += 1
            if cnt < 10:
                logger.info("Cannot get manifest from file. Retrying...")
                time.sleep(1.0)
            else:
                logger.error("Unable to get manifest from file '%s'. %s", local_filename, e)
    return manifest

def get_index():
    folder = "config/{repo}/".format(repo=config.BUILD_PATH)
    local_filename = os.path.join(folder, "index.json")
    logger.debug("Loading index from '%s'", local_filename)
    if not os.path.exists(local_filename):
        raise RuntimeError("Repository has not been synced")
    return json.load(open(local_filename))

def is_build_installed(build_name, executable_path):
    build_path = os.path.join(config.BSD_BATTLESERVER_FOLDER, build_name)
    executable_path = os.path.join(build_path, executable_path)
    if os.path.exists(executable_path):
        logger.debug("Build '%s' is installed", build_name)
        return True
    else:
        logger.info("Build '%s' is not installed", build_name)
        if os.path.exists("build_path"):
            logger.warning("Folder '%s exists but no .exe found!" % build_path)
        return False

def download_build(filename, ignore_if_exists=False):
    logger.info("Downloading build %s...", filename)
    bucket_name = config.BUILD_BUCKET
    conn = connect_to_region(config.S3_REGION_NAME, calling_format=OrdinaryCallingFormat())
    bucket = conn.get_bucket(bucket_name)
    path = filename#"ue4-builds/{repo}/{filename}".format(repo=repository, filename=filename)
    head, tail = os.path.split(path)
    dest_path = os.path.abspath(os.path.join(config.BSD_TEMP_FOLDER, tail))
    if os.path.exists(dest_path):
        if ignore_if_exists:
            return dest_path
        else:
            os.remove(dest_path)

    key = bucket.get_key(path)
    if not key:
        raise RuntimeError("Build '%s' not found on S3" % path)

    # Prepare destination folder and file.
    if not os.path.exists(config.BSD_TEMP_FOLDER):
        os.makedirs(config.BSD_TEMP_FOLDER)

    def cb(num_bytes, total):
        logger.debug("{:,} bytes of {:,} downloaded".format(num_bytes, total))

    with open(dest_path + ".tmp", "wb") as fp:
        key.get_file(fp=fp, cb=cb, num_cb=100)

    os.rename(dest_path + ".tmp", dest_path)

    return dest_path

def cleanup_s3(repository):
    """
    Slapped together to clean up old unused builds on S3
    """
    MAX_DAYS = 30

    bucket_name = config.BUILD_BUCKET
    path = "ue4-builds/{path}/WindowsServer/".format(path=config.BUILD_PATH) #! WindowsServer hardcoded
    index = get_index()
    conn = connect_to_region(config.S3_REGION_NAME, calling_format=OrdinaryCallingFormat())
    bucket = conn.get_bucket(bucket_name)
    now = datetime.datetime.utcnow()
    files = []
    for f in bucket.list(prefix=path, delimiter="/"): 
        dt = parser.parse(f.last_modified).replace(tzinfo=None)
        diff = now - dt

        filename = f.name.split("/")[-1]
        build_number = filename.split(".")[-2]

        if diff.days > MAX_DAYS:
            for entry in index["refs"]:
                if "."+build_number+"." in entry["build_manifest"]:
                    break
            else:
                files.append((filename, diff.days, f.name, build_number, dt))
                print("Deleting build %s from %s..." % (filename, dt))
                f.delete()

    files.sort(key=lambda x: x[1], reverse=True)
    print("Deleted %s files from S3" % len(files))
