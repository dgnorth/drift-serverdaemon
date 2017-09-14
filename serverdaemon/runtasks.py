# -*- coding: utf-8 -*-

import sys, os
import datetime, time, json, time, random
import argparse
import operator

import boto.ec2
import boto.iam
import boto3

import win32com.client as win
import getpass

from utils import get_local_refs
from logsetup import logger, log_event

TASK_FOLDER = "\\Drift"
PYTHON_PATH = r"c:\python27\python.exe"
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(os.path.realpath(__file__)), "..\\"))

def get_run_task_name(ref):
    name = "Run ref=%s,%s" % (ref[0], ref[1])
    return name

def get_run_tasks(scheduler):
    objTaskFolder = scheduler.GetFolder(TASK_FOLDER)
    colTasks = objTaskFolder.GetTasks(1)
    ret = [tuple(t.Name.split("=")[-1].split(",")) for t in colTasks if t.Name.startswith('Run ref=')]
    return set(ret)

def remove_ref_task(scheduler, ref):
    logger.warning("Removing task for ref '%s'" % str(ref))
    try:
        rootFolder = scheduler.GetFolder(TASK_FOLDER)
        task_id = get_run_task_name(ref)
        task = rootFolder.GetTask(task_id)
        logger.info("  Stopping task '%s'" % str(task_id))
        task.Stop(0)
        task.Enabled = False
        time.sleep(5.0)
        logger.info("  Deleting task '%s'" % str(task_id))
        rootFolder.DeleteTask(task_id, 0)

        logger.info("  Killing running processes ")
        from daemon import kill_processes_by_ref
        kill_processes_by_ref(ref[0], ref[1])
        logger.info("Done removing task for ref '%s'" % str(ref))

    except Exception as e:
        logger.error("Exception occurred removing task: %s" % e)

def add_ref_task(scheduler, ref):
    logger.warning("Adding task for ref '%s'" % str(ref))
    rootFolder = scheduler.GetFolder(TASK_FOLDER)

    action_id = get_run_task_name(ref)
    action_path = PYTHON_PATH
    action_arguments = os.path.join(ROOT_PATH, "run.py run --ref=%s --tenant=%s" % (ref[0], ref[1]))
    action_workdir = ROOT_PATH
    author = getpass.getuser()
    description = "Automatically created task from Drift Config"
    task_id = action_id.replace('/', '_')

    TASK_CREATE_OR_UPDATE = 6
    TASK_ACTION_EXEC = 0
    TASK_RUN_NO_FLAGS = 0

    taskDef = scheduler.NewTask(0)

    colTriggers = taskDef.Triggers
    taskDef.Principal.UserId="NT Authority\\SYSTEM"
    taskDef.Principal.RunLevel=1
    trigger = colTriggers.Create(1)
    trigger.StartBoundary = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    trigger.Repetition.Interval = "PT1M"
    trigger.Repetition.StopAtDurationEnd = False
    trigger.Enabled = True
    colActions = taskDef.Actions
    action = colActions.Create(TASK_ACTION_EXEC)
    action.ID = action_id
    action.Path = action_path
    action.WorkingDirectory = action_workdir
    action.Arguments = action_arguments
    info = taskDef.RegistrationInfo
    info.Author = 'System'
    info.Description = description
    settings = taskDef.Settings
    settings.Enabled = True
    settings.Hidden = False
    result = rootFolder.RegisterTaskDefinition(task_id, taskDef, TASK_CREATE_OR_UPDATE, "", "", TASK_RUN_NO_FLAGS)

    # start the task immediately
    task = rootFolder.GetTask(task_id)
    runningTask = task.Run("")
    logger.info("Task for ref '%s' is now running" % str(ref))

def update_tasks():
    scheduler = win.Dispatch("Schedule.Service")
    scheduler.Connect()

    actual_refs = get_run_tasks(scheduler)
    wanted_refs = get_local_refs()
    print "Currently installed refs: %s" % ", ".join(["%s:%s" % (r[0], r[1]) for r in actual_refs])
    print "I want to run the following refs: %s" % ", ".join(["%s:%s" % (r[0], r[1]) for r in wanted_refs])
    if actual_refs == wanted_refs:
        logger.info('Wanted refs match installed refs. Nothing to do.')
        sys.exit(0)
    refs_to_remove = actual_refs - wanted_refs
    refs_to_add = wanted_refs - actual_refs
    for ref in refs_to_remove:
        remove_ref_task(scheduler, ref)
        log_event("remove_ref_task", "Removed task for ref '%s'" % ref[0], ref=ref[0], tenant_name=ref[1])
    for ref in refs_to_add:
        add_ref_task(scheduler, ref)
        log_event("add_ref_task", "Added task for ref '%s'" % ref[0], ref=ref[0], tenant_name=ref[1])
