# -*- coding: utf-8 -*-
"""
    Drift game server management - Upload logfiles to S3 and delete
    ------------------------------------------------
"""
import datetime
import os
import sys

import psutil

import serverdaemon.config as config
from serverdaemon.logsetup import logger, flush_events
from serverdaemon.rest import get_machine_resource, get_battle_api
from serverdaemon.utils import get_ts, get_tags

MB = 1024 * 1024
TASK_FOLDER = "\\Drift"


def fmt_time(dt):
    try:
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return dt


def collect_machine_stats():
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")
    ret = {
        "disk_total_mb": disk.total/MB,
        "disk_free_mb": disk.free/MB,
        "memory_free_mb": mem.available/MB,
        "memory_total_mb": mem.total/MB,
        "cpu_percent": psutil.cpu_percent(interval=1),
        "boot_time": fmt_time(datetime.datetime.fromtimestamp(psutil.boot_time())),
    }
    return ret


def collect_tasks():
    try:
        import win32com.client as win
        scheduler = win.Dispatch("Schedule.Service")
        scheduler.Connect()

        objTaskFolder = scheduler.GetFolder(TASK_FOLDER)
        colTasks = objTaskFolder.GetTasks(1)
        ret = [t.Name for t in colTasks]
        return ret
    except:
        return None


def collect_installed_builds():
    try:
        ret = []
        path = os.path.join(config.BSD_BATTLESERVER_FOLDER)
        for folder in os.listdir(path):
            ret.append(folder)
        return ret
    except:
        return None


def collect_processes():
    ret = []
    for p in psutil.process_iter():
        with p.oneshot():
            try:
                name = p.name()
                exe = p.exe().replace("\\", "/").lower()
                cmd = p.cmdline()
            except psutil.AccessDenied:
                logger.debug("  Got AccessDenied for '%s'" % p.name())
                continue
            if not exe.startswith(config.BSD_BATTLESERVER_FOLDER.lower()): # name != "python.exe" and 
                logger.debug("Not collecting process '%s'" % exe)
                continue
            proc_info = {
                'create_time': datetime.datetime.fromtimestamp(p.create_time()).strftime("%Y-%m-%d %H:%M:%S"),
                'cpu_percent': p.cpu_percent(),
                'memory_mb': p.memory_info().vms/1024/1024,
                'username': p.username(),
                'name': name,
                'pid': p.pid,
                'cmd': cmd,
                'exe': exe
            }
            ret.append(proc_info)
    return ret


def heartbeat_all_tenants():
    ts = get_ts()
    tags = get_tags()
    product_name = tags.get("drift-product_name")
    group_name = tags.get("drift-group_name")

    if not product_name or not group_name:
        print("This machine is not configured to be an UE4 server! Missing necessary tags.")
        sys.exit(1)

    logger.info("Heartbeating all tenants in product '%s' with group '%s'", product_name, group_name)
    tenants_to_heartbeat = set()
    rows = ts.get_table('gameservers-instances').find({'group_name': group_name, 'product_name': product_name, 'region': config.region_name})
    for r in rows:
        tenants_to_heartbeat.add(r['tenant_name'])

    daemon_version = None
    daemon_last_modified = None
    file_name = 'VERSION'
    with open(file_name, 'r') as f:
        daemon_version = f.read().strip()
    try:
        mtime = os.path.getmtime(file_name)
    except OSError:
        mtime = 0
    daemon_last_modified = datetime.datetime.fromtimestamp(mtime)

    stats = collect_machine_stats()
    tasks = collect_tasks()
    installed_builds = collect_installed_builds()
    processes = collect_processes()
    config_info = {
        'tags': tags,
        'product_name': product_name,
        'driftconfig': {
            'version': ts.meta['version'],
            'last_modified': ts.meta['last_modified'],
        },
        'serverdaemon' : {
            'version': daemon_version,
            'last_modified': fmt_time(daemon_last_modified),
        },
        'tenants': list(tenants_to_heartbeat),
    }
    details = {
        'tasks': tasks,
        'installed_builds': installed_builds,
        'processes': processes,
    }

    events = flush_events()

    for tenant_name in tenants_to_heartbeat:
        driftbase_tenant = ts.get_table('tenants').find({'tenant_name': tenant_name, 'deployable_name': 'drift-base'})[0]
        root_endpoint = driftbase_tenant.get('root_endpoint')
        logger.info("Heartbeating tenant '%s' with root endpoint '%s'", tenant_name, root_endpoint)
        sess = get_battle_api(tenant_name)
        machine_resource = get_machine_resource(sess, root_endpoint, tenant_name)

        machine_resource.put(data={
                                    "group_name": group_name,
                                    "statistics": stats, 
                                    "config": config_info,
                                    "details": details,
                                    "events": events,
                            })

