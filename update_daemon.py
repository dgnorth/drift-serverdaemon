import os, sys, shutil
import zipfile, subprocess
from serverdaemon.logsetup import setup_logging, logger, log_event
import boto3
from boto3.s3.transfer import S3Transfer, TransferConfig
REGION = "eu-west-1"
BUCKET_NAME = "directive-tiers.dg-api.com"
UE4_BUILDS_FOLDER = "ue4-builds"

INSTALL_FOLDER = r"c:\drift-serverdaemon"

def get_my_version():
    t = [0, 0, 0]
    try:
        with open("VERSION") as f:
            version = f.read().strip()
        # increment version each time the script is called
        t = [int(p) for p in version.split(".")]
    except:
        logger.warning("Old version invalid")
    return t

def kill_python_processes():
    command = ["tasklist"]
    popen = subprocess.Popen(command, stdout=subprocess.PIPE)
    stdout, stderr = popen.communicate()
    lst = stdout.split("\n")
    for l in lst:
        ll = l.split()
        if not len(ll):
            continue
        name = ll[0]
        try:
            pid = int(ll[1])
        except:
            continue

        if pid == os.getpid():
            continue

        if "python.exe" in l:
            try:
                logger.info("Killing task '%s' with pid %s..." % (name, pid))
                command = ["taskkill", "/PID", str(pid), "/f"]
                subprocess.check_call(command, shell=True)
            except Exception as e:
                logger.error('Could not kill task. Error = %s' % e)

def check_download():
    client = boto3.client('s3', REGION)
    files = client.list_objects(Bucket=BUCKET_NAME, Prefix=UE4_BUILDS_FOLDER)['Contents']
    max_version = get_my_version()
    my_version = max_version
    logger.info("My version is %s", ".".join(str(p) for p in max_version))
    max_key = None
    for s3_key in files:
        filename = s3_key['Key']
        if "drift-serverdaemon-" in filename:
            lst = filename.split("-")[-1].split(".")
            try:
                file_version = [int(p) for p in lst[0:-1]]
            except ValueError:
                continue
            is_more = False
            if file_version[0] > max_version[0]:
                is_more = True
            elif file_version[1] > max_version[1]:
                is_more = True
            elif file_version[2] > max_version[2]:
                is_more = True
            if is_more:
                max_version = file_version
                max_key = filename
    if not max_key:
        logger.info("No new version found. Bailing out.")
        return None

    log_event("upgrade_daemon", "Upgrading Serverdaemon from version %s to %s" % (my_version, max_version), severity="WARNING")
    logger.info("found version %s, %s", max_version, max_key)
    transfer = S3Transfer(client)
    out_filename = "c:\\temp\\drift-serverdaemon.zip"
    transfer.download_file(BUCKET_NAME, max_key, out_filename)
    return out_filename

if __name__ == "__main__":
    setup_logging("updatedaemon")
    filename = check_download()
    if not filename:
        sys.exit(0)

    zip_file = zipfile.ZipFile(filename, 'r')
    for member in zip_file.namelist():
        # copy file (taken from zipfile's extract)
        filename = "/".join(member.split("/")[1:])
        source = zip_file.open(member)
        out_filename = os.path.join(INSTALL_FOLDER, filename)
        try:
            out_dirname = os.path.dirname(out_filename)
            os.makedirs(out_dirname)
        except:
            pass
        target = file(out_filename, "wb")
        with source, target:
            shutil.copyfileobj(source, target)
    zip_file.close()
    kill_python_processes()
    log_event("upgrade_daemon_complete", "Done Upgrading Serverdaemon. All python processes have been killed", severity="WARNING")