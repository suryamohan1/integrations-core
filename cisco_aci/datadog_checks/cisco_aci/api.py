# (C) Datadog, Inc. 2018
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)

import random
from requests import Request, Session

class Sess:
    def __init__(self, aci_url, session, apic_cookie, verify=None, timeout=None, log=None):
        self.session = session
        self.apic_cookie = apic_cookie
        self.aci_url = aci_url
        self.verify = verify
        self.timeout = timeout
        self.log = log

    def send(self, req):
        req.headers['Cookie'] = self.apic_cookie
        return self.session.send(req, verify=self.verify, timeout=self.timeout)

    def close(self):
        self.session.close()

    def make_request(self, path, raw_response=False, function_name=None):
        url = "{0}{1}".format(self.aci_url, path)
        req = Request('get', url)
        prepped = req.prepare()
        prepped.headers['Cookie'] = self.apic_cookie
        response = self.session.send(prepped, verify=self.verify, timeout=self.timeout)
        try:
            response.raise_for_status()
        except Exception as e:
            self.log.warning("Error making request: {0}".format(e))
            raise
        path_save = path.replace('/', '_')
        path_save = path_save.replace('?', '_')
        path_save = path_save.replace('&', '_')
        try:
            if raw_response:
                return response
            else:
                return response.json()
        except Exception as e:
            self.log.warning("Exception in json parsing, returning nothing: {0}".format(e))
            raise


class Api:
    def __init__(self, aci_urls, username, password, verify=False, timeout=10, log=None):
        self.aci_urls = aci_urls
        self.username = username
        self.password = password
        self.timeout = timeout
        self.verify = verify
        self.sessions = []
        if log:
            self.log = log
        else:
            import logging
            self.log = logging.getLogger('cisco_api')

    def close(self):
        for session in self.sessions:
            session.close()

    def login(self):
        # ensure sessions are an empty array
        self.sessions = []
        for aci_url in self.aci_urls:
            session = Session()
            data = '<aaaUser name="{0}" pwd="{1}"/>\n'.format(self.username, self.password)
            url = "{0}{1}".format(aci_url, '/api/aaaLogin.xml')
            req = Request('post', url, data=data)
            prepped_request = req.prepare()
            response = session.send(prepped_request, verify=self.verify, timeout=self.timeout)
            response.raise_for_status()
            self.apic_cookie = 'APIC-Cookie={}'.format(response.cookies.get('APIC-cookie'))
            sess = Sess(aci_url, session, self.apic_cookie,
                        verify=self.verify,
                        timeout=self.timeout,
                        log=self.log)
            self.sessions.append(sess)

    def make_request(self, path, raw_response=False, function_name=None):
        session = random.choice(self.sessions)
        return session.make_request(path, raw_response=raw_response, function_name=function_name)

    def get_apps(self, tenant, raw_response=False):
        path = "/api/mo/uni/tn-{0}.json?query-target=subtree&target-subtree-class=fvAp".format(tenant)
        response = self.make_request(path, raw_response)
        # return only the list of apps
        return self._parse_response(response, raw_response)

    def get_app_stats(self, tenant, app, raw_response=False):
        path = "/api/mo/uni/tn-{0}/ap-{1}.json?rsp-subtree-include=stats,no-scoped".format(tenant, app)
        response = self.make_request(path, raw_response)
        # return only the list of stats
        return self._parse_response(response, raw_response)

    def get_epgs(self, tenant, app, raw_response=False):
        path = "/api/mo/uni/tn-{0}/ap-{1}.json".format(tenant, app)
        query = '?query-target=subtree&target-subtree-class=fvAEPg'
        path = path + query
        response = self.make_request(path, raw_response)

        return self._parse_response(response, raw_response)

    def get_epg_stats(self, tenant, app, epg, raw_response=False):
        query = 'rsp-subtree-include=stats,no-scoped'
        path = "/api/mo/uni/tn-{0}/ap-{1}/epg-{2}.json?{3}"
        path = path.format(tenant, app, epg, query)

        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_epg_meta(self, tenant, app, epg, raw_response=False):
        query = 'query-target=subtree&target-subtree-class=fvCEp'
        path = "/api/mo/uni/tn-{0}/ap-{1}/epg-{2}.json?{3}"
        path = path.format(tenant, app, epg, query)
        response = self.make_request(path, raw_response)

        return self._parse_response(response, raw_response)

    def get_eth_list_for_epg(self, tenant, app, epg, raw_response=False):
        query = 'query-target=subtree&target-subtree-class=fvRsCEpToPathEp'
        path = "/api/mo/uni/tn-{0}/ap-{1}/epg-{2}.json?{3}"
        path = path.format(tenant, app, epg, query)
        response = self.make_request(path, raw_response)

        return self._parse_response(response, raw_response)

    def get_tenant_stats(self, tenant, raw_response=False):
        path = "/api/mo/uni/tn-{0}.json?rsp-subtree-include=stats,no-scoped".format(tenant)
        response = self.make_request(path, raw_response)
        # return only the list of stats
        return self._parse_response(response, raw_response)

    def get_tenant_events(self, tenant, page=0, page_size=15, raw_response=False):
        query1 = 'rsp-subtree-include=event-logs,no-scoped,subtree'
        query2 = 'order-by=eventRecord.created|desc'
        query3 = 'page={0}&page-size={1}'.format(page, page_size)
        query = '{0}&{1}&{2}'.format(query1, query2, query3)
        path = "/api/node/mo/uni/tn-{0}.json?{1}".format(tenant, query)
        response = self.make_request(path, raw_response)
        # return only the list of stats
        return self._parse_response(response, raw_response)

    def get_fabric_pods(self, raw_response=False):
        path = '/api/mo/topology.json?query-target=subtree&target-subtree-class=fabricPod'
        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_fabric_pod(self, pod, raw_response=False):
        path = '/api/mo/topology/pod-{0}.json'.format(pod)
        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_pod_stats(self, pod, raw_response=False):
        query = 'rsp-subtree-include=stats,no-scoped&page-size=20'
        path = '/api/mo/topology/pod-{0}.json?{1}'.format(pod, query)
        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_fabric_nodes(self, raw_response=False):
        path = '/api/mo/topology.json?query-target=subtree&target-subtree-class=fabricNode'
        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_fabric_node(self, pod, node, raw_response=False):
        path = '/api/mo/topology/pod-{0}/node-{1}.json'.format(pod, node)
        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_node_stats(self, pod, node, raw_response=False):
        query = 'rsp-subtree-include=stats,no-scoped&page-size=20'
        path = '/api/mo/topology/pod-{0}/node-{1}/sys.json?{2}'.format(pod, node, query)
        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_controller_proc_metrics(self, pod, node, raw_response=False):
        query = 'rsp-subtree-include=stats,no-scoped&rsp-subtree-class={0}'
        query = query.format('procMemHist5min,procCPUHist5min')
        path_base = '/api/node/mo/topology/pod-{0}/node-{1}/sys/proc.json?{2}'
        path = path_base.format(pod, node, query)

        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_spine_proc_metrics(self, pod, node, raw_response=False):
        query = 'rsp-subtree-include=stats,no-scoped&rsp-subtree-class={0}'
        query = query.format('procSysMemHist5min,procSysCPUHist5min')
        path_base = '/api/node/mo/topology/pod-{0}/node-{1}/sys/procsys.json?{2}'
        path = path_base.format(pod, node, query)

        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_eth_list(self, pod, node, raw_response=False):
        query = 'query-target=subtree&target-subtree-class=l1PhysIf'
        path = '/api/mo/topology/pod-{0}/node-{1}/sys.json?{2}'.format(pod, node, query)
        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_eth_stats(self, pod, node, eth, raw_response=False):
        query = 'rsp-subtree-include=stats,no-scoped&page-size=50'
        path = '/api/mo/topology/pod-{0}/node-{1}/sys/phys-[{2}].json?{3}'.format(pod, node, eth, query)
        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_eqpt_capacity(self, eqpt, raw_response=False):
        base_path = '/api/class/eqptcapacityEntity.json'
        base_query = 'query-target=self&rsp-subtree-include=stats&rsp-subtree-class='
        path_template = "{0}?{1}{2}"
        path = path_template.format(base_path, base_query, eqpt)
        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_capacity_contexts(self, context, raw_response=False):
        path_template = "/api/node/class/ctxClassCnt.json?rsp-subtree-class={0}"
        path = path_template.format(context)
        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_apic_capacity_limits(self, raw_response=False):
        base_path = "/api/mo/uni/fabric/compcat-default/fvsw-default/capabilities.json"
        query = "query-target=children&target-subtree-class=fvcapRule"
        path = "{0}?{1}".format(base_path, query)
        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def get_apic_capacity_metrics(self, capacity_metric, query=None, raw_response=False):
        if not query:
            query = "rsp-subtree-include=count"
        base_path = "/api/class/"
        path = "{0}{1}.json?{2}".format(base_path, capacity_metric, query)
        response = self.make_request(path, raw_response)
        return self._parse_response(response, raw_response)

    def _parse_response(self, response, raw_response=False):
        if raw_response:
            return response
        else:
            return response.get('imdata')
