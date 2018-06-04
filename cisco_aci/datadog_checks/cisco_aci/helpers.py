# (C) Datadog, Inc. 2018
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)

import re


def parse_capacity_tags(dn):
    tags = []
    pod = get_pod_from_dn(dn)
    if pod:
        tags.append("fabric_pod_id:{0}".format(pod))
    node = get_node_from_dn(dn)
    if node:
        tags.append("node_id:{0}".format(node))

    return tags


def get_pod_from_dn(dn):
    pod = re.search('pod-([0-9]+)', dn)
    if pod:
        return pod.group(1)
    else:
        return None


def get_bd_from_dn(dn):
    bd = re.search('/BD-([^/]+)/', dn)
    if bd:
        return bd.group(1)
    else:
        return None


def get_app_from_dn(dn):
    app = re.search('/ap-([^/]+)/', dn)
    if app:
        return app.group(1)
    else:
        return None


def get_cep_from_dn(dn):
    cep = re.search('/cep-([^/]+)/', dn)
    if cep:
        return cep.group(1)
    else:
        return None


def get_epg_from_dn(dn):
    epg = re.search('/epg-([^/]+)/', dn)
    if epg:
        return epg.group(1)
    else:
        return None


def get_ip_from_dn(dn):
    ip = re.search('/ip-([^/]+)/', dn)
    if ip:
        return ip.group(1)
    else:
        return None


def get_event_tags_from_dn(dn):
    tags = []
    node = get_node_from_dn(dn)
    if node:
        tags.append("node:" + node)
    app = get_app_from_dn(dn)
    if app:
        tags.append("app:" + app)
    bd = get_bd_from_dn(dn)
    if bd:
        tags.append("bd:" + bd)
    cep = get_cep_from_dn(dn)
    if cep:
        tags.append("mac:" + cep)
    ip = get_ip_from_dn(dn)
    if ip:
        tags.append("ip:" + ip)
    epg = get_epg_from_dn(dn)
    if epg:
        tags.append("epg:" + epg)
    return tags


def get_node_from_dn(dn):
    node = re.search('node-([0-9]+)', dn)
    if node:
        return node.group(1)
    else:
        return None


def get_hostname_from_dn(dn):
    pod = get_pod_from_dn(dn)
    node = get_node_from_dn(dn)
    return get_hostname(pod, node)


def get_hostname(pod, node):
    if pod and node:
        return "pod-{0}-node-{1}".format(pod, node)
    else:
        return None


def get_fabric_hostname(obj):
    attrs = get_attributes(obj)
    dn = attrs['dn']

    return get_hostname_from_dn(dn)


def get_attributes(obj):
    """
    the json objects look like this:
    {
    "objType": {
      "attributes": {
      ...
      }
    }
    It always has the attributes nested below the object type
    This helper provides a way of getting at the attributes
    """
    if obj.get('imdata'):
        obj = obj.get('imdata')
    keys = obj.keys()
    if len(keys) > 0:
        key = keys[0]
    else:
        return {}
    key_obj = obj.get(key, {})
    if type(key_obj) is not dict:
        # if the object is not a dict
        # it is probably already scoped to attributes
        return obj
    attrs = key_obj.get('attributes')
    if not attrs:
        # if the attributes doesn't exist,
        # it is probably already scoped to attributes
        return obj
    return attrs


def check_metric_can_be_zero(metric_name, metric_value, json_attributes):
    if "last" in metric_name or "Last" in metric_name:
        return True
    if not metric_value:
        return False
    if metric_value == 0 or metric_value == "0" or metric_value == "0.000000" or float(metric_value) == 0.0:
        if not json_attributes.get('cnt'):
            return False
        if json_attributes.get('cnt') == "0" or json_attributes.get('cnt') == 0:
            return False
    return True
