import os
import sys
from setuptools import setup, find_packages
from distutils.core import setup, Command
from pip.req import parse_requirements
import pip.download
import boto3
from boto3.s3.transfer import S3Transfer, TransferConfig

if 'deploy' not in sys.argv or 'sdist' not in sys.argv:
    print("You must call this setup script with both 'sdist' and 'deploy' commands")
    sys.exit(1)

def update_version():
    version = None

    try:
        with open("VERSION") as f:
            version = f.read().strip()
        # increment version each time the script is called
        t = [int(p) for p in version.split(".")]
        t[-1]+=1
        version = ".".join(str(p) for p in t)
    except:
        version = "0.1.0"

    with open("VERSION", "wb") as f:
        f.write(version + "\n")
    return version

version = update_version()

REGION = "eu-west-1"
BUCKET_NAME = "directive-tiers.dg-api.com"
UE4_BUILDS_FOLDER = "ue4-builds"

class DeployCommand(Command):
    description = "Deploy build to S3 so that daemons will pick it up and install"
    user_options = []
    def initialize_options(self):
        self.cwd = None
    def finalize_options(self):
        self.cwd = os.getcwd()
    def upload_build(self, local_filename, upload_filename):
        client = boto3.client('s3', REGION)
        base_name = "{}/{}".format(
            UE4_BUILDS_FOLDER, 
            upload_filename
            )
        transfer = S3Transfer(client)
        p = os.path.join('dist', local_filename)
        p = os.path.abspath(p)
        transfer.upload_file(p, BUCKET_NAME, base_name)
        print("Done uploading build '%s' to S3 as %s" % (local_filename, base_name))

    def run(self):
        assert os.getcwd() == self.cwd, 'Must be in package root: %s' % self.cwd
        local_filename = os.path.join('drift-serverdaemon-%s.zip' % version)
        remote_filename = 'drift-serverdaemon-%s.zip' % version #! temporary hack
        self.upload_build(local_filename, remote_filename)

        latest_filename = os.path.join('drift-serverdaemon-latest.zip')
        self.upload_build(local_filename, latest_filename)

setup_args = dict(
    name="drift-serverdaemon",
    version=version,
    author="Directive Games",
    author_email="info@directivegames.com",
    description="Server Daemon Application",
    packages=find_packages(
        exclude=["*.tests", "*.tests.*", "tests.*", "tests"]
    ),
    include_package_data=True,
    install_requires=[
        str(i.req)
        for i in parse_requirements(
            "requirements.txt", session=pip.download.PipSession()
        )
    ],
    cmdclass={
        'deploy': DeployCommand
    }

)

if __name__ == "__main__":
    setup(**setup_args)
