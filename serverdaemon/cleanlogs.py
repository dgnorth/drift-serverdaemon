# -*- coding: utf-8 -*-
"""
    Drift game server management - Upload logfiles to S3 and delete
    ------------------------------------------------
"""
import os
import os.path
import zipfile

import boto3

import config
from serverdaemon.logsetup import logger

# This is the S3 bucket name for server builds:
bucket_name = "battleserver-logs"

def upload_logs():
    s3 = boto3.resource('s3')
    log_folder = config.BSD_LOGS_FOLDER
    if not os.path.exists(log_folder):
        logger.info("Log folder '%s' not found" % log_folder)
        return

    for tenant in os.listdir(log_folder):
        full_path = os.path.join(log_folder, tenant)
        if not os.path.exists(full_path):
            logger.info("Skipping '%s' because it does not exist", tenant)
            continue

        for log_filename in os.listdir(full_path):
            if not log_filename.endswith(".log"): continue
            logger.info('Uploading %s...' % log_filename)
            full_filename = os.path.join(full_path, log_filename)
            try:
                f = open(full_filename, 'a')
            except:
                logger.info("Error opening '%s'", full_filename)
                continue
            f.close()

            zip_filename = log_filename + ".zip"
            full_zip_filename = os.path.join(full_path, zip_filename)
            try:
                os.remove(full_zip_filename)
            except:
                pass
            zf = zipfile.ZipFile(full_zip_filename, mode='w', compression=zipfile.ZIP_DEFLATED)
            zf.write(full_filename, arcname=log_filename)
            zf.close()
            s3.meta.client.upload_file(full_zip_filename, 'battleserver-logs', '{}/{}'.format(tenant, zip_filename))
            os.remove(full_filename)
            logger.info("Uploaded '%s' to S3", zip_filename)
