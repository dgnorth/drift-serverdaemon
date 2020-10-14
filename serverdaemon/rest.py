# -*- coding: utf-8 -*-
"""
    Drift game server management - REST Resoruces
    ------------------------------------------------
"""
import json

import requests

import serverdaemon.config as config
from serverdaemon.logsetup import logger
from serverdaemon.utils import get_machine_info, get_ts

DEFAULT_ROOT_ENDPOINT = "https://{}.dg-api.com/drift"


def get_root_endpoint(tenant):
    ts = get_ts()
    driftbase_tenant = ts.get_table('tenants').find({'tenant_name': tenant, 'deployable_name': 'drift-base'})[0]
    endpoint = driftbase_tenant.get('root_endpoint')
    if not endpoint:
        endpoint = DEFAULT_ROOT_ENDPOINT.format(tenant)
    return endpoint


def get_auth_token(tenant, role):
    """
    Gets a JWT token for 'role'.
    'role' is either 'battleserver' or 'battledaemon'.
    """
    ts = get_ts()
    driftbase_tenant = ts.get_table('tenants').find({'tenant_name': tenant, 'deployable_name': 'drift-base'})[0]
    auth_url = get_root_endpoint(tenant) + "/auth"

    #! TODO: Find user in organization config table

    if role == 'battleserver':
        credentials = config.battleserver_credentials
    elif role == "battledaemon":
        credentials = config.battledaemon_credentials
    else:
        raise RuntimeError("'role' %s not understood." % role)
    headers = {'Drift-Api-Key': config.api_key, 'Content-type': 'application/json'} #! TODO: Replace api key with product key
    r = requests.post(auth_url, data=json.dumps(credentials), headers=headers)
    r.raise_for_status()
    return r.json()


def get_battle_api(tenant, token=None):
    """Returns a requests session for the battle service REST API."""
    sess = requests.Session()
    if not token:
        token = get_auth_token(tenant, "battledaemon")["jti"]
    sess.headers.update({
        'Content-type': 'application/json',
        'Accept': 'application/json',
        'Authorization': 'JTI {}'.format(token),
        'Drift-Api-Key': config.api_key
    })
    return sess


def get_machine_resource(sess, battle_api_host, tenant):
    machine_info = get_machine_info()

    # If an identical machine resource exists, use that.
    params = {
        "rows": 1,
        "realm": "",
        "instance_id": "",
        "instance_type": "",
        "instance_name": "",
        "placement": "",
        "public_ip": "",
        "group_name": "",
        "machine_info": {},
    }
    params.update(machine_info)
    # TODO: use the 'sess' to make the GET request so we have auth in place.
    # Using 'sess' now will result in 400: Bad Request, probably because the
    # params are passed as json and not as url query params.
    r = sess.request("GET", battle_api_host + "/machines", data=json.dumps(params))

    if r.status_code == 200 and len(r.json()) > 0:
        machine = r.json()[0]
        machine_url = machine.get("url", machine.get("uri")) #! backwards compability with old uri
        machine_resource = MachineResource(sess, machine_url, tenant, create=False)
    else:
        logger.info("Got back status code %s from GET so I will create a new machine resource" % r.status_code)
        machine_resource = MachineResource(sess, battle_api_host + "/machines", tenant, machine_info)

    return machine_resource


class RESTResource(object):
    tenant = None
    location = None
    _response = None
    data = None
    def __init__(self, session, url, tenant, params=None, create=True):
        self._sess = session
        self.tenant = tenant
        if create:
            r = self._request(method="post", url=url, data=params, expect=[201])
            self.location = r.headers["location"]
            self._response = r
        else:
            self.location = url
        self.data = self.get().json()

    def __str__(self):
        return "RESTResource %s" % self.location

    def _request(self, method, url, data, expect=None, retry=False):
        expect = expect or [200]
        r = self._sess.request(method, url, data=json.dumps(data, indent=4))
        if r.status_code not in expect:
            if "Invalid JTI" in r.text:
                if not retry:
                    logger.warning("Authorization header '%s' is invalid. Reauthenticating...", self._sess.headers["Authorization"])
                    token = get_auth_token(self.tenant, "battledaemon")["jti"]
                    self._sess.headers["Authorization"] = "JTI {}".format(token)
                    return self._request(method, url, data, expect, True)
                else:
                    logger.error("Authorization header '%s' still invalid after reauthentication. Bailing out!", self._sess.headers["Authorization"])
            args = (method.upper(), url, r.status_code, r.text)
            raise RuntimeError("Can't %s to %s, err=%s, text=%s" % args)
        return r

    def get(self, data=None, expect=None):
        logger.info("[GET] %s", self.location)
        return self._request(method="get", url=self.location, data=data, expect=expect)

    def put(self, data=None, expect=None):
        logger.info("[PUT] %s", self.location)
        return self._request(method="put", url=self.location, data=data, expect=expect)

    def patch(self, data=None, expect=None):
        logger.info("[PATCH] %s", self.location)
        return self._request(method="patch", url=self.location, data=data, expect=expect)


class ServerResource(RESTResource):
    def __init__(self, session, tenant, info, url=None):
        create = False
        if not url:
            url = get_root_endpoint(tenant) + "/servers"
            create = True
        RESTResource.__init__(self, session, url, tenant, info, create=create)

    def set_status(self, status, new_details):
        details = self.get().json()["details"]
        details.update(new_details)
        self.put({"status": status, "details": details})

    def get_status(self):
        return self.get().json()["status"]


class MachineResource(RESTResource):
    def __init__(self, session, url, tenant, info=None, create=True):
        RESTResource.__init__(self, session, url, tenant, info, create=create)

    def heartbeat(self):
        self.put({})
