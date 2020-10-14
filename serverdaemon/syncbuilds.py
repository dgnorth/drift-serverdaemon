# -*- coding: utf-8 -*-
import os
import shutil
import sys
from zipfile import ZipFile

from serverdaemon import config
from serverdaemon.logsetup import logger, log_event
from serverdaemon.s3 import get_manifest, is_build_installed, download_build
from serverdaemon.utils import get_ts
from serverdaemon.utils import update_state, get_local_refs

"""

    {
        "bucket_name": "directive-tiers.dg-api.com", 
        "command_line": "", 
        "path": "ue4-builds/directivegames/dg-driftplugin", 
        "product_name": "dg-driftplugin", 
        "s3_region": "eu-west-1"
    }, 

"""


def install_build(zipfile_name, ignore_if_exists=False):
    """
    Install server build on local drive. 'zipfile_name' is the name of the
    zip file in 'BSD_TEMP_FOLDER'.
    The function returns the folder name of the battleserver build image.
    If 'ignore_if_exists' is True, then the function returns immediately if the
    build is already installed on local drive.

    Details:
    The build is installed into a subfolder in BSD_BATTLESERVER_FOLDER using
    the same name as the zip file (sans the .zip ending). The contents of the
    zip file is first extracted to a temporary folder, then that folder is
    renamed to the final name. This is to ensure an atomic publishing of the
    build. If the target folder already exists, it will be removed first.
    """
    head, tail = os.path.split(zipfile_name)
    image_name, ext = os.path.splitext(tail)

    # The final destination of the build
    dest_folder = os.path.join(config.BSD_BATTLESERVER_FOLDER, image_name)
    dest_folder = os.path.abspath(dest_folder)
    if ignore_if_exists and os.path.exists(dest_folder):
        return image_name

    zipfile_path = os.path.join(config.BSD_TEMP_FOLDER, zipfile_name)
    zipfile_path = os.path.abspath(zipfile_path)
    if not os.path.exists(zipfile_path):
        raise RuntimeError("Zipfile '{}' not found!".format(zipfile_path))


    with ZipFile(zipfile_path) as zipfile:
        update_state(
            state='PROGRESS',
            meta={'file': tail, 'step': 'unzipping'},
        )

        # Extract to a staging folder
        staging_folder = dest_folder + ".temp"

        try:
            logger.info("Unzipping %s to %s", zipfile_path, staging_folder)
            zipfile.extractall(staging_folder)
            # Publish the build
            update_state(
                state='PROGRESS',
                meta={'file': tail, 'step': 'publishing'},
            )
            if os.path.exists(dest_folder):
                logger.info("Removing previous install at %s", dest_folder)
                shutil.rmtree(dest_folder, ignore_errors=False)
            logger.info("Publishing %s to %s", staging_folder, dest_folder)
            os.rename(staging_folder, dest_folder)
        finally:
            # Remove staging folder, if needed.
            if os.path.exists(staging_folder):
                logger.debug("Removing staging folder %s", staging_folder)
                shutil.rmtree(staging_folder)

    return image_name


def download_latest_builds(force=False):
    ts = get_ts()
    product_name = config.product_name
    group_name = config.group_name

    # get the S3 location where the builds for this product are located
    rows = ts.get_table('ue4-build-artifacts').find({'product_name': product_name})
    if not rows:
        logger.error("No UE4 build artifacts configured for product '%s'" % product_name)
        sys.exit(1)
    bucket_name = rows[0]['bucket_name']
    path = rows[0]['path']
    s3_region = rows[0]['s3_region']

    refs = get_local_refs()
    if refs:
        logger.info('Syncing builds for the following refs: %s' % repr(refs))

    for ref, tenant in refs:
        build_info = get_manifest(ref)
        if build_info is None:
            logger.info("Build %s not found. Ignoring ref.", ref)
            continue
        build_name = build_info["build"]
        print("Checking out build '%s'" % build_name)
        if not force and is_build_installed(build_name, build_info["executable_path"]):
            logger.info("Build '%s' already installed" % build_name)
            continue
        log_details = {"archive": build_info["archive"]}
        log_event("download_build", "Downloading build for ref '%s'" % ref, details=log_details, tenant_name=tenant)

        local_filename = download_build(build_info["archive"], ignore_if_exists=(not force))
        log_details["local_filename"] = local_filename
        log_event("download_build_complete", "Finished downloading build for ref '%s'" % ref, details=log_details, tenant_name=tenant)
        logger.info("Done downloading '%s' to %s" % (build_info["archive"], local_filename))

        install_build(local_filename)


        log_event("install_build_complete", "Finished installing build for ref '%s'" % ref, details=log_details, tenant_name=tenant)