import os, sys
sys.dont_write_bytecode = True # no pyc files please
import argparse
import subprocess
import json
import psutil
import logging
import time
import traceback

import serverdaemon.daemon as daemon
from serverdaemon.s3 import get_manifest, sync_index, get_index, cleanup_s3
from serverdaemon.cleanlogs import upload_logs
from serverdaemon.utils import get_ts
from serverdaemon.logsetup import setup_logging, logger, log_event
from serverdaemon import logsetup
import serverdaemon.config as config
from serverdaemon.config import config_file
from serverdaemon.heartbeat import heartbeat_all_tenants
from serverdaemon.syncbuilds import download_latest_builds
from serverdaemon.runtasks import update_tasks

def delete_old_builds():
    daemon.delete_old_builds()

def delete_all_builds():
    yes = raw_input("Are you sure you want to delete all builds from this machine? [Y/n]")
    if yes == "Y":
        logger.warning("Deleting all builds...")
        daemon.delete_all_builds()
    else:
        print "I didn't think so!"
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser()
    #parser.add_argument("cmd", choices=["run", "deploy", "killall"])
    parser.add_argument("-v", "--verbose", help="increase output verbosity", action="store_true")
    subparsers = parser.add_subparsers(help='sub-command help', dest="cmd")

    parser_run = subparsers.add_parser('run', help='Run a battleserver')
    parser_run.add_argument("-r", "--ref", help='The server ref to run')
    #parser_run.add_argument("-n", "--num-processes", help='Number of UE4 processes to run simultaneously. Overrides num-processes from config')
    parser_run.add_argument("-t", "--tenant", help='Backend tenant to connect to. Overrides tenant from config')

    subparsers.add_parser('clean', help='Delete old builds from the machine')
    subparsers.add_parser('cleanall', help='Delete all builds from the machine')
    subparsers.add_parser('cleanlogs', help='Clean logs and move to S3')
    subparsers.add_parser('cleans3', help='Delete old builds from S3')
    subparsers.add_parser('heartbeat', help='Heartbeat this machine on all registered tenants')
    subparsers.add_parser('updateruntasks', help='Set up run tasks for all registered refs')
    

    parser_deploy = subparsers.add_parser('syncbuilds', help='Fetch and install the latest builds from S3')
    parser_deploy.add_argument("-f", "--force", action="store_true", help='Always download file (even if it already exists)')

    args = parser.parse_args()
    logname = args.cmd
    tenant_name = getattr(args, "tenant", None)
    ref = getattr(args, "ref", None)

    logsetup.args_ref = ref
    logsetup.args_tenant_name = tenant_name
    logsetup.args_cmd = logname

    #! we have multiple ongoing run commands at once and we can't use the same logfile
    if args.cmd in ("run"):
        logname = "%s_%s"  % (args.cmd, os.getpid())
    setup_logging(logname)
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    # start by syncing down the index file
    logger.info("serverdaemon starting. cmd = '%s'. Product = '%s', Tenant = '%s', Repository = '%s'" % 
                (args.cmd, config.product_name, tenant_name, config.BUILD_PATH))

    try:
        sync_index()
    except Exception as e:
        logger.error("Error! %s" % e)
        logger.exception("Error! %s" % e)

    if args.cmd == "run":
        index_file = get_index()
        build_info = get_manifest(args.ref)
        if not build_info:
            msg = "Build not found for ref '%s'" % args.ref
            logger.error(msg)
            sys.exit(1)
        logger.info("RUNNING build %s", build_info)
        build_path = build_info["build"]
        d = daemon.Daemon(args.ref, tenant_name)
        d.run()
        logger.info("Exiting")

    elif args.cmd == "syncbuilds":
        download_latest_builds(args.force)
    elif args.cmd == "clean":
        delete_old_builds()
    elif args.cmd == "cleanall":
        delete_all_builds()
    elif args.cmd == "cleanlogs":
        upload_logs()
    elif args.cmd == "cleans3":
        cleanup_s3()
    elif args.cmd == "heartbeat":
        heartbeat_all_tenants()
    elif args.cmd == "updateruntasks":
        update_tasks()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        tb = traceback.format_exception(exc_type, exc_value, exc_traceback)
        log_event("exception", "Unhandled exception in Daemon: %s" % str(e), details={"traceback": tb}, severity="ERROR")
        logger.exception(e)
        raise