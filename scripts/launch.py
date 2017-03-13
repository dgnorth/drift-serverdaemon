# -*- coding: utf-8 -*-

import sys, os
sys.dont_write_bytecode = True # no pyc files please

import datetime, time, json, random
import argparse
import operator
import getpass

try:
    import boto3
    from tabulate import tabulate
except ImportError:
    print "Failed to import libraries. Please run pip install -r requirements.txt"
    sys.exit(1)

WINDOWS_BASE_IMAGE_NAME = 'Windows_Server-2016-English-Full-Base-*'
WINDOWS_BASE_IMAGE_NAME = 'Windows_Server-2012-R2_RTM-English-64Bit-Base-*'
AMI_OWNER_CANONICAL = 'amazon'

REGION_NAME = 'eu-west-1'

SERVICE_NAME = 'ue4server'

REGION_CHOICES = ['eu-west-1', 'ap-southeast-1', 'us-west-1']
INSTANCE_TYPE_CHOICES = ['t2.small', 't2.medium', 'c4.large', 'c4.xlarge']

TIER_NAME = 'DEVNORTH' #!

product_name = None

def fold_tags(tags):
    """Fold boto3 resource tags array into a dictionary."""
    return {tag['Key']: tag['Value'] for tag in tags}

def unfold_tags(tags):
    """Unfold a sensible dictionary into boto3 resource tags."""
    ret = []
    for k, v in tags.iteritems():
        ret.append({'Key': k, 'Value': v})
    return ret

def filterize(d):
    """
    Return dictionary 'd' as a boto3 "filters" object by unfolding it to a list of
    dict with 'Name' and 'Values' entries.
    """
    return [{'Name': k, 'Values': [v]} for k, v in d.items()]

def find_ami(ec2):
    print "Finding the latest AMI on AWS that matches", WINDOWS_BASE_IMAGE_NAME
    filters = [
        {'Name': 'name', 'Values': [WINDOWS_BASE_IMAGE_NAME]}, 
    ]
    amis = list(ec2.images.filter(Owners=[AMI_OWNER_CANONICAL], Filters=filters))
    if not amis:
        print "No AMI found matching '{}'. Not sure what to do now.".format(WINDOWS_BASE_IMAGE_NAME)
        sys.exit(1)        
    ami = max(amis, key=operator.attrgetter("creation_date"))
    return ami

def find_security_groups(ec2):
    filters = {'tag:service-name': 'ue4server'}
    ret = list(ec2.security_groups.filter(Filters=filterize(filters)))
    return ret

def launch_instance(group_name, region_name, instance_type):

    key_name = 'ue4server-%s' % region_name[:-2]

    ec2 = boto3.resource('ec2', region_name=region_name)

    ami = find_ami(ec2)
    security_groups = find_security_groups(ec2)
    security_group_ids = [g.id for g in security_groups]
    vpc_ids = set([g.vpc_id for g in security_groups])
    if len(vpc_ids) != 1:
        raise RuntimeError("UE4 Security groups must belong to exactly 1 VPC. %s VPC's found" % len(vpc_ids))
    vpc_id = list(vpc_ids)[0]
    vpc_resource = ec2.Vpc(vpc_id)
    subnets = list(vpc_resource.subnets.all())

    for s in subnets:
        if s.tags:
            tags = fold_tags(s.tags)
            name = tags['Name']
            if 'public' in name:
                subnet_id = s.id
                print "Picking subnet '%s' (%s) because I think its public" % (name, s.id)
                break
    else:
        subnet_id = random.choice(subnets).id
        print "Picked subnet '%s' by random because I found no public ones" % (subnet_id)

    print "Using source AMI:"
    print "\tID:\t", ami.id
    print "\tName:\t", ami.name
    print "\tDate:\t", ami.creation_date
    print "Security Groups: %s" % (", ".join(security_group_ids))
    print "VPC ID: %s" % vpc_id

    user_data = ""
    with open("userdata.txt", "r") as f:
        user_data = f.read()

    instances = ec2.create_instances(
        DryRun=False,
        ImageId=ami.id,
        MinCount=1,
        MaxCount=1,
        KeyName=key_name,
        UserData=user_data,
        InstanceType=instance_type,
        Monitoring={
            'Enabled': True
        },
        NetworkInterfaces=[
        {
            'DeviceIndex': 0,
            'SubnetId': subnet_id,
            'AssociatePublicIpAddress': True,
            'Groups': security_group_ids,
        }
        ],
        IamInstanceProfile = {
            'Name': 'ec2'
        },
    )
    instance = instances[0]
    state = instance.state["Name"]
    sys.stdout.write("Instance is being launched.")
    while state == 'pending':
        time.sleep(1)
        sys.stdout.write(".")
        instance.reload()
        state = instance.state["Name"]

    instance_name = instance.private_dns_name
    instance_id = instance.id

    print "\nInstance '%s' (%s) is now in state '%s'" % (instance_name, instance_id, state)
    if state != 'running':
        print 'Unexpected state!'
        sys.exit(1)

    tags = {
        'Name': '{}-{}-{}'.format(TIER_NAME, SERVICE_NAME, product_name),
        'service-name': SERVICE_NAME,
        'tier': TIER_NAME,
        'drift-group_name': group_name,
        'drift-product_name': product_name,
        'drift-status': 'launching',
        'launched-by': getpass.getuser()
    }
    instance.create_tags(Tags=unfold_tags(tags))
    
    post_action_report()

    print "\n" + "*"*80
    print "Instance '%s' (%s) will now be initialized." % (instance_name, instance_id)
    print "This process will take up to 10-20 minutes and should be completed before %s" % ((datetime.datetime.now()+datetime.timedelta(minutes=20)).strftime("%H:%M"))
    print "Run 'launch.py %s list' to see setup status. Setup is complete when 'drift status' reaches 'ready' " % product_name
    print "In order to finalize setup you might need to add the machine group '%s' to the config for your product" % group_name
    print "If you have tenants for the product configured for this group they will get machine heartbeats once setup is done"
    print "*"*80

def list_instances(group_name=None, region_name=None, instance_id=None, state=None):
    regions = REGION_CHOICES
    if region_name:
        regions = [region_name]
    instances = []
    for region in regions:
        ec2 = boto3.resource('ec2', region_name=region)
        filters = [{'Name': 'instance-state-name', 'Values': ['running']}]
        filters = [
            {'Name': 'tag:drift-product_name', 'Values': [product_name]}
        ]
        if group_name:
            filters.append({'Name': 'tag:drift-group_name', 'Values': [group_name]})
        if instance_id:
            filters.append({'Name': 'instance-id', 'Values': [instance_id]})
        if state:
            filters.append({'Name': 'instance-state-name', 'Values': [state]})

        found_instances = ec2.instances.filter(Filters=filters)
        for instance in found_instances:
            tags = fold_tags(instance.tags)
            # instances.append({
            #     "instance_id": instance.id,
            #     "instance_type": instance.instance_type,
            #     "group_name": tags.get("drift-group_name"),
            #     "region_name": region,
            #     "state": instance.state['Name']
            #     })
            instances.append([instance.id,
                              instance.instance_type, 
                              tags.get('drift-group_name'), 
                              region, 
                              tags.get('launched-by'), 
                              instance.launch_time.strftime("%Y-%m-%d %H:%M"),
                              instance.state['Name'], 
                              tags.get('drift-status') if instance.state['Name'] == 'running' else '' ])
    instances.sort()
    if instances:
        print
        print tabulate(instances, headers=["instance id", "instance type", "group name", "region name", "launched by", "launch time", "state", "drift status"])
        print
    else:
        print "No instances found"
    return instances

def terminate_instance(instance_id):
    instances = list_instances(instance_id=instance_id)
    if len(instances) != 1:
        return
    yes = raw_input("Are you sure you want to terminate instance '%s'? [Y/n]: " % instance_id)
    if yes != "Y":
        print "User cancelled"
        return
    region_name = instances[0][3]
    print "Terminating instance '%s' in region %s..." % (instance_id, region_name)
    ec2 = boto3.resource('ec2', region_name=region_name)
    ec2.instances.filter(InstanceIds=[instance_id]).terminate()

    post_action_report()

def check_state(state, intended_state):
    if state != intended_state:
        print "Instance needs to be in state '%s' but is in state '%s'. Cannot continue." % (intended_state, state)
        sys.exit(2)

def stop_instance(instance_id):
    instances = list_instances(instance_id=instance_id)
    if len(instances) != 1:
        return
    check_state(instances[0][6], 'running')

    region_name = instances[0][3]
    print "Stopping instance '%s' in region %s..." % (instance_id, region_name)
    ec2 = boto3.resource('ec2', region_name=region_name)
    ec2.instances.filter(InstanceIds=[instance_id]).stop()

    post_action_report()

def start_instance(instance_id):
    instances = list_instances(instance_id=instance_id)
    if len(instances) != 1:
        return
    check_state(instances[0][6], 'stopped')

    region_name = instances[0][3]
    print "Restarting instance '%s' in region %s..." % (instance_id, region_name)
    ec2 = boto3.resource('ec2', region_name=region_name)
    ec2.instances.filter(InstanceIds=[instance_id]).start()

    post_action_report()

def post_action_report():
    time.sleep(1.0)
    print "\nCurrent status for product '%s':" % product_name
    list_instances()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("product", help='Name of the product')

    subparsers = parser.add_subparsers(help='sub-command help', dest="cmd")
    parser_launch = subparsers.add_parser('launch', help='Launch a new battleserver machine')
    parser_launch.add_argument("-g", "--group", required=True, help='Name of the group which runs on this machine')
    parser_launch.add_argument("-r", "--region", required=True, help='Amazon region to launch the instance in', choices=REGION_CHOICES)
    parser_launch.add_argument("-i", "--instancetype", required=True, help='Amazon region to launch the instance in', choices=INSTANCE_TYPE_CHOICES)

    parser_list = subparsers.add_parser('list', help='List battleserver machines')
    parser_list.add_argument("-g", "--group", required=False, help='Name of the group to filter on')
    parser_list.add_argument("-r", "--region", required=False, help='Amazon region to filter on', choices=REGION_CHOICES)
    parser_list.add_argument("-s", "--state", required=False, help='Machine state to filter on (e.g. running)')

    p = subparsers.add_parser('terminate', help='Terminate a battleserver machine')
    p.add_argument("instance_id", help='Instance ID to terminate')

    p = subparsers.add_parser('stop', help='Stop a battleserver machine')
    p.add_argument("instance_id", help='Instance ID to stop')

    p = subparsers.add_parser('start', help='Restart a battleserver machine that has previously been stopped')
    p.add_argument("instance_id", help='Instance ID to start')

    args = parser.parse_args()

    global product_name
    product_name = args.product

    if args.cmd == 'launch':
        launch_instance(args.group, args.region, args.instancetype)
    elif args.cmd == 'list':
        list_instances(args.group, args.region, state=args.state)
    elif args.cmd == 'terminate':
        terminate_instance(args.instance_id)
    elif args.cmd == 'stop':
        stop_instance(args.instance_id)
    elif args.cmd == 'start':
        start_instance(args.instance_id)

if __name__ == "__main__":
    main()
