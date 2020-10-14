# -*- coding: utf-8 -*-
"""
    Drift game server management - Main Daemon
    ------------------------------------------------
"""
import copy
import datetime
import os
import os.path
import shutil
import socket
import subprocess
import sys
import time
from threading import Thread

import dateutil.parser
import psutil

import serverdaemon.config as config
from serverdaemon.logsetup import logger, log_event
from serverdaemon.rest import ServerResource, get_auth_token, get_battle_api, get_machine_resource, get_root_endpoint
from serverdaemon.s3 import get_index
from serverdaemon.s3 import get_manifest
from serverdaemon.utils import get_num_processes

try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty  # python 3.x

# Battleserver UDP port range
MIN_PORT = 7777
MAX_PORT = 8000


def delete_all_builds():
    shutil.rmtree(config.BSD_BATTLESERVER_FOLDER, ignore_errors=True)
    shutil.rmtree(config.BSD_TEMP_FOLDER, ignore_errors=True)


def delete_old_builds():
    """
    deletes all 'user' builds that do not match the current build_number
    Currently leaves other refs alone
    """
    def extract_build_from_filename(filename):
        lst = filename.split(".")
        try:
            return int(lst[-2])
        except ValueError:
            return int(lst[-1])
    repo = config.BUILD_PATH
    logger.info("Deleting old user builds for repo '%s'...", repo)
    index_file = get_index()
    build_folders = os.listdir(config.BSD_BATTLESERVER_FOLDER)
    zip_files = os.listdir(config.BSD_TEMP_FOLDER)
    build_number_by_ref = {}
    num_deleted_folders = 0
    num_deleted_files = 0
    for ref in index_file["refs"]:
        ref_name = ref["ref"]
        target_platform = ref["target_platform"]
        if ref_name.startswith("users/") and target_platform == "WindowsServer":
            build_number = extract_build_from_filename(ref["build_manifest"])
            if ref_name in build_number_by_ref:
                build_number_by_ref[ref_name] = min(build_number_by_ref[ref_name], build_number)
            else:
                build_number_by_ref[ref_name] = build_number

    for ref_name, latest_build_number in build_number_by_ref.items():
        logger.debug("Latest build for ref '%s' is %s", ref_name, latest_build_number)
        ref_filename = ref_name.replace("/", ".")
        for folder in build_folders:
            if ref_filename in folder:
                this_build_number = extract_build_from_filename(folder)
                if this_build_number < latest_build_number:
                    folder = os.path.join(config.BSD_BATTLESERVER_FOLDER, folder)
                    logger.info("Deleting folder '%s' for ref '%s' because %s < %s", folder, ref_name, this_build_number, latest_build_number)
                    shutil.rmtree(folder)
                    num_deleted_folders += 1

        for filename in zip_files:
            if ref_filename in filename:
                this_build_number = extract_build_from_filename(filename)
                if this_build_number < latest_build_number:
                    filename = os.path.join(config.BSD_TEMP_FOLDER, filename)
                    logger.info("Deleting zip file '%s' for ref '%s' because %s < %s", filename, ref_name, this_build_number, latest_build_number)
                    os.remove(filename)
                    num_deleted_files += 1

    if any((num_deleted_folders, num_deleted_files)):
        logger.info("Deleted %s build folders and %s zip files", num_deleted_folders, num_deleted_files)
    else:
        logger.info("No old builds to delete")


def _get_logfolder():
    if not os.path.exists(config.BSD_LOGS_FOLDER):
        os.makedirs(config.BSD_LOGS_FOLDER)

    return config.BSD_LOGS_FOLDER


def _get_available_port(min_port, max_port):
    """Find an unused UPD port number."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    for i in range(250):
        port_no = min_port + i
        try:
            sock.bind(('', port_no))
            sock.close()
            return port_no
        except socket.error:
            pass

    raise RuntimeError(
        "Exhausted trying to find available UPD port number in the range "
        "of %s to %s." % (min_port, max_port)
        )


def kill_processes_by_ref(ref, tenant):
    """"
    Find all running processes of any version of 'ref' and terminate
    """
    logger.info("kill_processes_by_ref '%s', '%s'", ref, tenant)
    repo = config.BUILD_PATH
    build_info = get_manifest(ref)
    executable_path = build_info["executable_path"].lower()
    partial_build = build_info["build"].replace(str(build_info["build_number"]), "").lower()
    logger.info("  Finding partial path '%s'..." % partial_build)
    killed_processes = []
    #! TODO: tenant is not included so this kills all tasks in this ref for all tenants. Fix me!
    for p in psutil.process_iter():
        try:
            exe = p.exe().replace("\\", "/").lower()
            cmd = p.cmdline()
        except psutil.AccessDenied:
            logger.debug("  Got AccessDenied for '%s'" % p.name())
            continue

        if partial_build in exe and ("-tenant=%s" % tenant) in cmd:
            killed_processes.append({'pid': p.pid, 'exe': exe, 'cmd': cmd})
            logger.info("  Killing pid %s: '%s'", p.pid, p.exe())
            p.terminate()
            p.wait(timeout=10)

    if len(killed_processes):
        log_event('processes_killed', 
                  'Killed %s processes' % len(killed_processes),
                  details={'processes': killed_processes}, 
                  severity='WARNING', 
                  ref=ref, tenant_name=tenant)

    logger.info("Done killing processes for ref='%s', tenant='%s'. Killed %s processes", ref, tenant, len(killed_processes))


def find_build_manifest(index_file, ref):
    for r in index_file["refs"]:
        if r["ref"] == ref:
            return r["build_manifest"]
    return -1


class Daemon(object):
    battleserver_instances = {}
    ref = None
    tenant = None
    num_processes = None

    def __init__(self, ref, tenant):
        self.ref = ref
        self.tenant = tenant
        self.num_processes = get_num_processes(ref, tenant)
        # kill old processes which have not been cleaned up correctly
        kill_processes_by_ref(self.ref, self.tenant)
        logger.info("Daemon starting on ref '%s' with tenant '%s' and %d processes", self.ref, self.tenant, self.num_processes)


    def shutdown_servers_and_exit(self, message=""):
        logger.warning("Shutting down because: '%s'" % message)
        log_event("shutdown_servers", "Shutting down all servers because: '%s'" % message, severity="WARNING")
        kill_processes_by_ref(self.ref, self.tenant)
        for pid, (q, battleserver_resource, status) in self.battleserver_instances.items():
            battleserver_resource.set_status("killed", {"status-reason": message})
        sys.exit(1)

    def start_battleserver(self):
        repo = config.BUILD_PATH
        build_info = get_manifest(self.ref)
        def enqueue_output(out, queue):
            for line in iter(out.readline, b''):
                queue.put(line)
            queue.put("ProcessExit")
            out.close()

        #! get command line from config
        command_line = config.config_file["command-line"]
        build_path = build_info["build"]
        executable_path = build_info["executable_path"]
        command, battleserver_resource = get_battleserver_command(build_path, executable_path, command_line, self.tenant)

        logger.debug("Spawning process with command: %s", command)

        try:
            p = subprocess.Popen(command, stdout=subprocess.PIPE, bufsize=1)
        except Exception as e:
            logger.exception("Spawning failed.")
            battleserver_resource.set_status("popen failed", {"error": str(e)})
            raise

        pid = p.pid

        status = "starting"

        battleserver_resource.put({
                "repository": repo,
                "ref": self.ref,
                "build": build_path,
                "build_number": build_info["build_number"],
                "target_platform": build_info["target_platform"],
                "build_info": build_info,
                "status": status, 
                "pid": pid, 
                "details": {"ref": self.ref, "repository": repo, "build_path": build_path}
                })
        logger.info("Spawned process with pid %s" % pid)
        q = Queue()
        t = Thread(target=enqueue_output, args=(p.stdout, q))
        t.daemon = True # thread dies with the program
        t.start()
        return pid, q, battleserver_resource

    def run(self):

        try:
            build_info = get_manifest(self.ref)
            build_path = build_info["build"]

            index_file = get_index()

            command_line = config.config_file["command-line"]
            status = "starting"

            build_path = build_info["build"]
            executable = os.path.join(config.BSD_BATTLESERVER_FOLDER, build_info["build"], build_info["executable_path"])
            if not os.path.exists(executable):
                log_event("build_not_installed", "Build '%s' not installed. Cannot start daemon." % build_info["build"])
                return

            start_time = time.time()
            loop_cnt = 0
            # read line without blocking
            while 1:
                loop_cnt += 1
                diff = (time.time() - start_time)
                p = None
                config_num_processes = get_num_processes(self.ref, self.tenant)
                if config_num_processes != self.num_processes:
                    txt = "Number of processes in config for ref '%s' has changed from %s to %s" % (self.ref, self.num_processes, config_num_processes)
                    logger.warning(txt)
                    log_event("num_processes_changed", txt)
                    # if we should run more processes: no problem, we'll add them in automatically
                    # but if we should run fewer processes we need to kill some
                    self.num_processes = config_num_processes

                    if len(self.battleserver_instances) > self.num_processes:
                        servers_killed = []
                        while len(self.battleserver_instances) > self.num_processes:
                            logger.info("I am running %s battleservers but should be running %s. Killing servers..." % (len(self.battleserver_instances), self.num_processes))
                            # try to find a server that is not 'running'. If no such servers are found then kill a running one
                            for pid, (q, battleserver_resource, status) in self.battleserver_instances.items():
                                resource_status = battleserver_resource.get_status()
                                if resource_status != "running":
                                    logger.info("Found battleserver in state '%s' to kill: %s" % (resource_status, battleserver_resource))
                                    pid_to_kill = pid
                                    break
                            else:
                                logger.warning("Found no battleserver to kill that was not 'running'. I will kill a running one")
                                pid_to_kill = self.battleserver_instances.keys()[0]

                            try:
                                p = psutil.Process(pid_to_kill)
                                q, battleserver_resource, status = self.battleserver_instances[pid_to_kill]
                                logger.info("Killing server with pid %s" % pid_to_kill)
                                p.terminate()
                                servers_killed.append(str(pid_to_kill))
                                battleserver_resource.set_status("killed", {"status-reason": "Scaling down"})
                            except psutil.NoSuchProcess:
                                logger.info("Cannot kill %s because it's already dead")

                            del self.battleserver_instances[pid_to_kill]
                            time.sleep(5.0)
                        txt = "Done killing servers for ref '%s'. Killed servers %s and am now running %s servers" % (self.ref, ", ".join(servers_killed), len(self.battleserver_instances))
                        log_event("servers_killed", txt)

                if self.num_processes == 0:
                    logger.info("Running zero processes")
                    time.sleep(10)
                    continue

                if len(self.battleserver_instances) < self.num_processes:
                    num_added = 0
                    while len(self.battleserver_instances) < self.num_processes:
                        logger.info("I am running %s battleservers but should be running %s. Adding servers..." % (len(self.battleserver_instances), self.num_processes))
                        pid, q, battleserver_resource = self.start_battleserver()
                        self.battleserver_instances[pid] = (q, battleserver_resource, "starting")
                        num_added += 1
                        time.sleep(5.0)
                    logger.info("Done adding servers. Running instances: %s" % ",".join([str(p) for p in self.battleserver_instances.keys()]))

                    txt = "Done adding servers for ref '%s'. Added %s servers and am now running %s servers" % (self.ref, num_added, len(self.battleserver_instances))
                    log_event("servers_added", txt)

                for pid, (q, battleserver_resource, status) in self.battleserver_instances.items():
                    try:
                        p = psutil.Process(pid)
                    except psutil.NoSuchProcess:
                        logger.info("Process %s running server '%s' has died", pid, battleserver_resource)
                        resource_status = battleserver_resource.get_status()
                        if resource_status == "starting":
                            battleserver_resource.set_status("abnormalexit", {"status-reason": "Failed to start"})
                        if resource_status == "running":
                            battleserver_resource.set_status("abnormalexit", {"status-reason": "Died prematurely"})
                        # else the instance has updated the status
                        time.sleep(5.0)
                        logger.info("Restarting UE4 Server (1)...")
                        del self.battleserver_instances[pid]
                        break

                new_index_file = get_index()
                old_manifest = find_build_manifest(index_file, self.ref)
                new_manifest = find_build_manifest(new_index_file, self.ref)

                if old_manifest != new_manifest:
                    build_info = get_manifest(self.ref)
                    build_path = build_info["build"]

                    logger.info("Index file has changed. Reloading")
                    self.shutdown_servers_and_exit("New build is available")
                while 1:
                    if not self.battleserver_instances:
                        break
                    empty = True
                    for pid, (q, battleserver_resource, status) in self.battleserver_instances.items():
                        try:
                            line = q.get(timeout=.1)
                        except Empty:
                            #sys.stdout.write(".")
                            print("%s..." % pid)
                            time.sleep(1.0)
                        else: # got line
                            empty = False
                            logger.debug("stdout: %s", line)
                            if "Game Engine Initialized." in line:
                                logger.info("Game server has started up!")
                                status = "started"
                                self.battleserver_instances[pid] = (q, battleserver_resource, status)
                            if line == "ProcessExit":
                                logger.info("UE4 Process has exited")
                                resource_status = battleserver_resource.get_status()
                                if resource_status == "starting":
                                    battleserver_resource.set_status("abnormalexit", {"status-reason": "Failed to start"})
                                # else the instance has updated the status
                                time.sleep(5.0)
                                logger.info("Restarting UE4 Server (2)...")
                                try:
                                    p = psutil.Process(pid)
                                    if p: p.terminate()
                                except:
                                    pass
                                del self.battleserver_instances[pid]
                                empty = True
                                break
                    if empty:
                        time.sleep(1.0)
                        break
                for pid, (q, battleserver_resource, status) in self.battleserver_instances.items():
                    if status == "starting" and diff > 60.0:
                        logger.error("Server still hasn't started after %.0f seconds!" % diff)
                        sys.exit(-1)
                    elif status == "started" and loop_cnt % 10 == 0:
                        resp = battleserver_resource.get().json()
                        if len(resp["pending_commands"]) > 0:
                            for cmd in resp["pending_commands"]:
                                logger.warning("I should execute the following command: '%s'", cmd["command"])
                                command_resource = copy.copy(battleserver_resource)
                                command_resource.location = cmd["url"]
                                command_resource.patch(data={"status": "running"})

                                if cmd["command"] == "kill":
                                    logger.error("External command to kill servers!")
                                    self.shutdown_servers_and_exit("Received command to kill all")

                        resource_status = resp["status"]
                        if diff > 60.0 and resource_status == "starting":
                            logger.error("Server is still in status '%s' after %.0f seconds!" % (resource_status, diff))
                            battleserver_resource.set_status("killed", {"status-reason": "Failed to reach 'started' status"})
                            time.sleep(5.0)
                            logger.info("Restarting UE4 Server (4)...")
                            try:
                                p = psutil.Process(pid)
                                if p: p.terminate()
                            except:
                                pass
                            del self.battleserver_instances[pid]
                        else:
                            heartbeat_date = dateutil.parser.parse(resp["heartbeat_date"]).replace(tzinfo=None)
                            heartbeat_diff = (datetime.datetime.utcnow()-heartbeat_date).total_seconds()
                            if heartbeat_diff > 60:
                                logger.error("Server heartbeat is %s seconds old. The process must be frozen", heartbeat_diff)
                                battleserver_resource.set_status("killed", {"status-reason": "Heartbeat timeout"})
                                time.sleep(5.0)
                                logger.info("Restarting UE4 Server (5)...")
                                try:
                                    p = psutil.Process(pid)
                                    if p: p.terminate()
                                except:
                                    pass
                                del self.battleserver_instances[pid]

        except KeyboardInterrupt:
            logger.info("User exiting...")
            self.shutdown_servers_and_exit("User exit")
        except Exception as e:
            # unhandled exception
            logger.exception("Fatal error occurred in run_battleserver_loop. Exiting")
            self.shutdown_servers_and_exit("Fatal error, '%s' occurred in run_battleserver_loop" % e)


def get_battleserver_command(image_name, executable_path, command_line, tenant, **kw):
    command_line = command_line or []
    tenant = tenant or "default"

    executable = os.path.join(config.BSD_BATTLESERVER_FOLDER, image_name, executable_path)
    if not os.path.exists(executable):
        raise RuntimeError("Executable '%s' not found. Build might not be installed" % executable)
    logger.info("Absolute path of executable: %s" % executable)

    # Make an explicit parameter type check so we can fail with a sensible error
    if not isinstance(command_line, list):
        raise RuntimeError("Argument 'command_line' must be a list.")

    # Register machine and server info
    sess = get_battle_api(tenant)
    battle_api_host = get_root_endpoint(tenant)
    machine_resource = get_machine_resource(sess, battle_api_host, tenant)
    logger.info("Machine resource: %s", machine_resource)
    public_ip = machine_resource.data.get("public_ip")

    # Construct a command line
    command = [executable] + command_line
    if public_ip:
        command += ["-publicIP=%s" % public_ip]

    jti_token = get_auth_token(tenant, "battleserver")["jti"]
    # See UE4 command line arguments at http://tinyurl.com/oygdwy3
    port = _get_available_port(MIN_PORT, MAX_PORT)

#Battle_Lava+End+Lobby+Login+Main -server -log -Messaging -nomcp -pak -CrashForUAT -SessionId=B0166D674598A24A73B8D29174F9826E -SessionOwner="matth" -SessionName="deditcatedad server"
    battleserver_info = {
          "status": "pending",
          "image_name": image_name,
          "command_line": " ".join(command),
          "command_line_custom": " ".join(command_line),
          "machine_id": machine_resource.data["machine_id"],
          #"celery_task_id": self.request.id,
    }
    if public_ip:
        battleserver_info["public_ip"] = public_ip
    battleserver_info["port"] = port

    #battleserver_resource = RESTResource(sess, battle_api_host"/servers", battleserver_info)
    battleserver_resource = ServerResource(sess, tenant, battleserver_info)
    logger.debug("Battleserver resource: %s", battleserver_resource)

    server_id = battleserver_resource.data["server_id"]
    token = battleserver_resource.data["token"]
    command += [
        "-drift_url={}".format(battle_api_host),
        "-server_url={}".format(battleserver_resource.location),
        "-token={}".format(token),
    ]
    command += [
        "-server",
        "-port={}".format(port),
        #"-logfolder={}".format(_get_logfolder(image_name)),  # Vk Specific
        "-FORCELOGFLUSH",  # Force a log flush after each line.
        "-unattended",  # Disable anything requiring feedback from user.
        "-tenant={}".format(tenant),  # Select this tenant
        "-jti={}".format(jti_token),  # Access token for REST API calls.
        #"-log",
        #"-Messaging"
        "-abslog={}/{}/server_{}.log".format(_get_logfolder(), tenant, server_id),
        "-CrashForUAT",
    ]
    battleserver_resource.put({"status": "pending", "command_line": " ".join(command)})

    return command, battleserver_resource


def list_tempfolder():
    """
    Return contents of the download temp folder as generated by the
    os.walk() function.
    """
    for path, subs, files in os.walk(config.BSD_TEMP_FOLDER):
        return files

    return []


def list_battleserver_builds():
    """
    Return a list of subfolders under the battleserver build images folder.
    """
    for path, subs, files in os.walk(config.BSD_BATTLESERVER_FOLDER):
        return subs

    return []
