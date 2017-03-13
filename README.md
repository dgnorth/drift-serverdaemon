# drift-serverdaemon
Drift Powered Server daemon for UE4 Server management running on AWS

Currently the daemon runs on Windows and uses powershell scripts and scheduled tasks to manage processes. However, there is very little platform-specific functionality in the daemon itself so migrating it to a Linux system should be simple.

## Launching a new Instance
In the future the Server daemon will use Autoscaling Groups for ec2 instance configuration but currently this is not available.

In the meantime the python script `scripts\launch.py` allows you to easily manage your ec2 instances.

Run the script with `launch.py --help` to get information about usage.

Battleserver EC2 instances are tagged on a **product** and **group** but each instance can run multiple battleserver versions and against multiple tenants on the product.

Products and groups are configured through drift-config (on the Kaleo website for example).

You should treat your battleserver instances as ephemeral and not do any custom modifications to running instances, but rather use the `launch.py` command to terminate and then launch new ones.

Launching instances takes around 10-20 minutes, depending on the location of the ec2 (much longer on ap-southeast-1 for example) and you can monitor the progress by running `launch.py [product] --list`. Once the `drift status` column has reached *ready* state the daemon will start to heartbeat against all tenants on the product that are configured to use the specified *group*.

# Deploying new server-daemon code
One of the scheduled tasks that are running every minute will check for, and install new drift-serverdaemon versions if available.
 - If you want to update the serverdaemon you can 'quickdeploy' it from your local machine by running `setup.py sdist --formats=zip deploy`
 - This will upload a zip file containing a new version to S3 and within a minute all ec2's should download and install it.
 - **All running UE4 servers will be killed and restarted when the daemon is updated.**
 - Be careful not to damage the update_daemon.py script when updating since all servers will install the new script and will then not be able to update the daemon after that.

## Debugging
 If you ran through the steps above and are not getting any battleservers after waiting for at least 20 minutes here are some things to try:
 - If the *drift status* column in `launch.py [product] list` is not *ready* that means that some part of the software installation failed. If it is *ready* that means that all the tasks were installed and the problem is in running the tasks,
 - Take a look at the logs for the instance in splunk and see if you are getting any drift-serverdaemon or battleserver logs. If you are seeing neither then the installation might have failed.
 - You should remote desktop into the instance (you will need access to the AWS console and iam key) and see if there are any scheduled tasks under the Drift folder and if there is a drift-serverdaemon folder in c:\
 - If not you should take a look at the user scripts output log in `C:\Program Files\Amazon\Ec2ConfigService\Logs\Ec2ConfigLog.txt`. At the bottom you should see the output of our script.
 - If things did install correctly and you see drift-serverdaemon and builds folders in c:\ then you should look at the serverdaemon logs in the c:\logs folder.
 - See if you spot any python or unreal processes in the task manager.

### If you want to run the refs manually to see the output here are some steps to take.
 - Disable all the scheduled tasks in the Drift folder in the Task Scheduler.
 - Try running a battleserver using one of your refs. For example: ```python.exe C:\drift-serverdaemon\run.py run -r users.alice```
 - Search for the Port number in the ue4 server log: `C:\logs\battleserver\myue4project` and connect to it from a local client to see if it works.
 - See if there are logs from this host on splunk already
 - Look through the serverdaemon logs in c:\logs\drift-serverdaemon
 - Use the task manager and show 'command line' column to see what python and Unreal Engine processes are running. If weird stuff is happening maybe it's because there is an old python process running that is still spawning Unreal processes. Try ending these.
 - You can try restarting the ec2 instance. It should start running its assigned refs automatically.