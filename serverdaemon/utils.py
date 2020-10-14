# -*- coding: utf-8 -*-
import subprocess
from socket import gethostname

import boto.ec2
import requests
from driftconfig.util import get_domains

import config
from serverdaemon.logsetup import logger

ec2_metadata = "http://169.254.169.254/latest/meta-data/"

def get_local_refs():
    ts = get_ts()
    region_name = config.region_name
    product_name = config.product_name
    group_name = config.group_name

    # find the refs that tenants want to run on this group in this region
    rows = ts.get_table('gameservers-instances').find({'group_name': group_name,
                                                       'product_name': product_name, 
                                                       'region': region_name})
    refs = set()
    if not rows:
        logger.error("No Gameserver instances configured for product '%s' and group '%s' on region '%s'" % (product_name, group_name, region_name))
        return refs

    for r in rows:
        if not r.get('enabled', False):
            logger.warning('Task %s, %s is disabled', r['ref'], r['tenant_name'])
            continue
        refs.add((r['ref'], r['tenant_name']))
    return refs

def update_state(state, meta):
    #! This appears to be some placeholder
    print("update_state: %s - %s" % (state, meta))

def get_repository():
    ts = get_ts()
    rows = ts.get_table('ue4-build-artifacts').find({'product_name': config.product_name})
    if not rows:
        raise RuntimeError("No UE4 build artifacts configured for product '%s'" % config.product_name)

    return rows[0]['bucket_name'], rows[0]['path'], rows[0]['s3_region']

def get_api_key():
    api_key_version = "service" # instead of version we use this special moniker to override all version rules in api router
    ts = get_ts()
    rows = ts.get_table('api-keys').find({'product_name': config.product_name, 'key_type': 'product', 'in_use': True})
    if not rows:
        raise RuntimeError("Cannot find API Key for product '%s'" % config.product_name)
    return '{}:{}'.format(rows[0]['api_key_name'], api_key_version)

def get_battledaemon_credentials():
    return get_battleserver_credentials()

def get_battleserver_credentials():
    ts = get_ts()
    tier_name = config.get_tier_name()
    rows = ts.get_table('tiers').find({'tier_name': tier_name})
    if not rows:
        raise RuntimeError('Tier %s not present in config' % (tier_name))
    service_user = rows[0]['service_user']
    return {
            "username": service_user['username'],
            "password": service_user['password'],
            "provider": "user+pass",
        }

def get_ts():
    domains = get_domains().values()
    if len(domains) != 1:
        raise RuntimeError("Unexpected number of domains in drift config: %s" % len(domains))
    ts = list(domains)[0]["table_store"]
    return ts

def get_num_processes(ref, tenant):
    ts = get_ts()
    region_name = config.region_name
    product_name = config.product_name
    group_name = config.group_name
    rows = ts.get_table('gameservers-instances').find({'group_name': group_name,
                                                       'product_name': product_name, 
                                                       'region': region_name,
                                                       'ref': ref,
                                                       'tenant_name': tenant})
    if not rows:
        raise RuntimeError('Ref %s for tenant %s is not registered on this machine!' % (ref, tenant))
    ret = int(rows[0]['processes_per_machine'])
    return ret

def get_region():
    #return 'eu-west-1' #!!!!!!!!!
    try:
        r = requests.get(
            ec2_metadata + "placement/"
            "availability-zone", timeout=0.5
        )
        region = r.text.strip()[:-1]  # skip the a, b, c at the end
        return region
    except Exception as e:
        logger.error("Cannot find region. %s" % e)
        return None

def get_tags():
    try:
        r = requests.get(
            ec2_metadata + "placement/"
            "availability-zone", timeout=0.5
        )
        region = r.text.strip()[:-1]  # skip the a, b, c at the end
        r = requests.get(
            ec2_metadata + "instance-id",
            timeout=0.5
        )
        instance_id = r.text.strip()
        try:
            conn = boto.ec2.connect_to_region(region)
            ec2 = conn.get_all_reservations(filters={"instance-id": instance_id})[0]
            tags = ec2.instances[0].tags
            return tags
        except Exception:
            log.warning("Could not find a tier tag on the EC2 Instance %s.", instance_id)
            raise
    except requests.exceptions.RequestException as e:
        host_name = gethostname()
        tier_name = "DEVNORTH"
        logger.warning("Could not query EC2 metastore. Assuming tier is '%s'" % tier_name)
        #raise RuntimeError("Could not query EC2 metastore: %s" % e)
    ret = {
        "tier": "DEVNORTH",
        "drift-product_name": "dg-driftplugin",
        "drift-group_name": "dev",
    }
    logger.warning("Not running on EC2. Returning hard coded temp values for tags: %s" % repr(ret))
    return ret

def get_tier_name():
    """
    Get tier name from an AWS EC2 tag
    """
    tags = get_tags()
    tier_name = str(tags.get("tier", "DEVNORTH"))

    return tier_name

def get_machine_details():
    ret = {}
    try:
        import psutil
    except ImportError:
        logger.error("psutil not available. Cannot get machine into")
        return ret
    import platform
    ret["cpu_count"] = psutil.cpu_count(logical=False)
    ret["cpu_count_logical"] = psutil.cpu_count(logical=True)
    ret["total_memory_mb"] = psutil.virtual_memory().total//1024//1024
    ret["machine_name"] = platform.node()
    ret["processor"] = platform.processor()
    ret["platform"] = platform.platform()
    ret["python_version"] = platform.python_version()
    ret["system"] = platform.system()
    name = subprocess.check_output(["wmic","cpu","get", "name"]).strip().split("\n")[1]
    ret["cpu_name"] = name

    return ret


def get_machine_info():
    """Return info for the /machine endpoint in battle service."""

    realm = "local"
    tags = get_tags()
    group_name = tags.get('drift-group_name', 'unknown')
    # Detect exotic realms
    try:
        r = requests.get(ec2_metadata)
        if r.status_code == 200:
            realm = "aws"
    except Exception:
        pass

    import socket
    private_ip = socket.gethostbyname(socket.gethostname())
    # Get machine based on realm
    info = {
        "realm": realm,
        "private_ip": private_ip,
        "group_name": group_name,
    }

    if realm == "local":
        info.update({
            "instance_name": socket.gethostname(),
        })
    elif realm == "aws":
        info.update({
            "instance_id": requests.get(ec2_metadata + "instance-id").text,
            "instance_type": requests.get(ec2_metadata + "instance-type").text,
            "instance_name": requests.get(ec2_metadata + "hostname").text,
            "placement": requests.get(ec2_metadata + "placement/availability-zone").text,
            "public_ip": requests.get(ec2_metadata + "public-ipv4").text,
            "machine_info": get_machine_details()
        })

    return info
