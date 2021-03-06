# (C) Datadog, Inc. 2018
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
import json
import os
import sys

import mock
import pytest
from datadog_checks.kubelet import KubeletCheck
from datadog_checks.kubelet.prometheus import CadvisorPrometheusScraper
from datadog_checks.checks.prometheus import PrometheusScraper

# Skip the whole tests module on Windows
pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='tests for linux only')

# Constants
HERE = os.path.abspath(os.path.dirname(__file__))
QUANTITIES = {
    '12k': 12 * 1000,
    '12M': 12 * (1000 * 1000),
    '12Ki': 12. * 1024,
    '12K': 12.,
    '12test': 12.,
}

NODE_SPEC = {
    u'cloud_provider': u'GCE',
    u'instance_type': u'n1-standard-1',
    u'num_cores': 1,
    u'system_uuid': u'5556DC4F-C198-07C8-BE37-ACB98B1BA490',
    u'network_devices': [{u'mtu': 1460, u'speed': 0, u'name': u'eth0', u'mac_address': u'42:01:0a:84:00:04'}],
    u'hugepages': [{u'num_pages': 0, u'page_size': 2048}],
    u'memory_capacity': 3885424640,
    u'instance_id': u'8153046835786593062',
    u'boot_id': u'789bf9ff-77be-4f43-8352-62f84d5e4356',
    u'cpu_frequency_khz': 2600000,
    u'machine_id': u'5556dc4fc19807c8be37acb98b1ba490'
}

EXPECTED_METRICS_COMMON = [
    'kubernetes.cpu.capacity',
    'kubernetes.cpu.usage.total',
    'kubernetes.cpu.limits',
    'kubernetes.cpu.requests',
    'kubernetes.filesystem.usage',
    'kubernetes.filesystem.usage_pct',
    'kubernetes.memory.capacity',
    'kubernetes.memory.limits',
    'kubernetes.memory.requests',
    'kubernetes.memory.usage',
    'kubernetes.network.rx_bytes',
    'kubernetes.network.tx_bytes'
]

EXPECTED_METRICS_PROMETHEUS = [
    'kubernetes.memory.usage_pct',
    'kubernetes.network.rx_dropped',
    'kubernetes.network.rx_errors',
    'kubernetes.network.tx_dropped',
    'kubernetes.network.tx_errors',
    'kubernetes.io.write_bytes',
    'kubernetes.io.read_bytes',
    'kubernetes.apiserver.certificate.expiration.count',
    'kubernetes.apiserver.certificate.expiration.sum',
    'kubernetes.rest.client.requests',
    'kubernetes.kubelet.runtime.operations',
    'kubernetes.kubelet.runtime.errors'
]


@pytest.fixture
def aggregator():
    from datadog_checks.stubs import aggregator
    aggregator.reset()
    return aggregator


def mock_kubelet_check(monkeypatch, instances):
    """
    Returns a check that uses mocked data for responses from prometheus endpoints, pod list,
    and node spec.
    """
    check = KubeletCheck('kubelet', None, {}, instances)
    monkeypatch.setattr(check, 'retrieve_pod_list', mock.Mock(return_value=json.loads(mock_from_file('pods.json'))))
    monkeypatch.setattr(check, '_retrieve_node_spec', mock.Mock(return_value=NODE_SPEC))
    monkeypatch.setattr(check, '_perform_kubelet_check', mock.Mock(return_value=None))

    # Mock response for "/metrics/cadvisor"
    attrs = {
        'close.return_value': True,
        'iter_lines.return_value': mock_from_file('cadvisor_metrics.txt').split('\n')
    }
    mock_resp = mock.Mock(headers={'Content-Type': 'text/plain'}, **attrs)
    monkeypatch.setattr(check.cadvisor_scraper, 'poll', mock.Mock(return_value=mock_resp))

    # Mock response for "/metrics"
    attrs = {
        'close.return_value': True,
        'iter_lines.return_value': mock_from_file('kubelet_metrics.txt').split('\n')
    }
    mock_resp = mock.Mock(headers={'Content-Type': 'text/plain'}, **attrs)
    monkeypatch.setattr(check.kubelet_scraper, 'poll', mock.Mock(return_value=mock_resp))

    return check


def mock_from_file(fname):
    with open(os.path.join(HERE, 'fixtures', fname)) as f:
        return f.read()


def test_bad_config():
    with pytest.raises(Exception):
        KubeletCheck('kubelet', None, {}, [{}, {}])


def test_parse_quantity():
    for raw, res in QUANTITIES.iteritems():
        assert KubeletCheck.parse_quantity(raw) == res


def test_kubelet_default_options():
    check = KubeletCheck('kubelet', None, {}, [{}])
    check.NAMESPACE = 'kubernetes'
    assert check.cadvisor_scraper.NAMESPACE == 'kubernetes'
    assert check.kubelet_scraper.NAMESPACE == 'kubernetes'

    assert isinstance(check.cadvisor_scraper, CadvisorPrometheusScraper)
    assert isinstance(check.kubelet_scraper, PrometheusScraper)


def test_kubelet_check_prometheus(monkeypatch, aggregator):
    instance_with_tag = {"tags": ["instance:tag"]}
    check = mock_kubelet_check(monkeypatch, [instance_with_tag])
    monkeypatch.setattr(check, 'process_cadvisor', mock.Mock(return_value=None))

    check.check(instance_with_tag)

    assert check.cadvisor_legacy_url is None
    check.retrieve_pod_list.assert_called_once()
    check._retrieve_node_spec.assert_called_once()
    check._perform_kubelet_check.assert_called_once()
    check.cadvisor_scraper.poll.assert_called_once()
    check.kubelet_scraper.poll.assert_called_once()
    check.process_cadvisor.assert_not_called()

    # called twice so pct metrics are guaranteed to be there
    check.check(instance_with_tag)
    for metric in EXPECTED_METRICS_COMMON:
        aggregator.assert_metric(metric)
        aggregator.assert_metric_has_tag(metric, "instance:tag")
    for metric in EXPECTED_METRICS_PROMETHEUS:
        aggregator.assert_metric(metric)
        aggregator.assert_metric_has_tag(metric, "instance:tag")
    assert aggregator.metrics_asserted_pct == 100.0


def test_prometheus_cpu_summed(monkeypatch, aggregator):
    check = mock_kubelet_check(monkeypatch, [{}])
    monkeypatch.setattr(check, 'rate', mock.Mock())

    with mock.patch("datadog_checks.kubelet.prometheus.get_tags", side_effect=mocked_get_tags):
        check.check({"cadvisor_metrics_endpoint": "http://dummy", "kubelet_metrics_endpoint": ""})

    # Make sure we submit the summed rates correctly:
    # - fluentd-gcp-v2.0.10-9q9t4 uses two cpus, we need to sum (1228.32 + 825.32) * 10**9 = 2053640000000
    # - demo-app-success-c485bc67b-klj45 is mono-threaded, we submit 7.756358313 * 10**9 = 7756358313
    #
    calls = [
        mock.call('kubernetes.cpu.usage.total', 2053640000000.0, ['pod_name:fluentd-gcp-v2.0.10-9q9t4']),
        mock.call('kubernetes.cpu.usage.total', 7756358313.0, ['pod_name=demo-app-success-c485bc67b-klj45']),
    ]
    check.rate.assert_has_calls(calls, any_order=True)

    # Make sure the per-core metrics are not submitted
    bad_calls = [
        mock.call('kubernetes.cpu.usage.total', 1228320000000.0, ['pod_name:fluentd-gcp-v2.0.10-9q9t4']),
        mock.call('kubernetes.cpu.usage.total', 825320000000.0, ['pod_name:fluentd-gcp-v2.0.10-9q9t4']),
    ]
    for c in bad_calls:
        assert c not in check.rate.mock_calls


def test_kubelet_check_instance_config(monkeypatch):
    def mock_kubelet_check_no_prom():
        check = mock_kubelet_check(monkeypatch, [{}])

        monkeypatch.setattr(check.cadvisor_scraper, 'process', mock.Mock(return_value=None))
        monkeypatch.setattr(check.kubelet_scraper, 'process', mock.Mock(return_value=None))
        monkeypatch.setattr(check, 'process_cadvisor', mock.Mock(return_value=None))

        return check

    check = mock_kubelet_check_no_prom()
    check.check({"cadvisor_port": 0, "cadvisor_metrics_endpoint": "", "kubelet_metrics_endpoint": ""})

    assert check.cadvisor_legacy_url is None
    check.retrieve_pod_list.assert_called_once()
    check._retrieve_node_spec.assert_called_once()
    check._perform_kubelet_check.assert_called_once()
    check.process_cadvisor.assert_not_called()
    check.cadvisor_scraper.process.assert_not_called()
    check.kubelet_scraper.process.assert_not_called()

    check = mock_kubelet_check_no_prom()
    check.check({"cadvisor_port": 0, "metrics_endpoint": "", "kubelet_metrics_endpoint": "http://dummy"})

    check.cadvisor_scraper.process.assert_not_called()
    check.kubelet_scraper.process.assert_called()


def mocked_get_tags(entity, _):
    tag_store = {
        "kubernetes_pod://2edfd4d9-10ce-11e8-bd5a-42010af00137": [
            "pod_name:fluentd-gcp-v2.0.10-9q9t4"
        ],
        'docker://5741ed2471c0e458b6b95db40ba05d1a5ee168256638a0264f08703e48d76561': [
            'pod_name:fluentd-gcp-v2.0.10-9q9t4'
        ],
        "docker://5f93d91c7aee0230f77fbe9ec642dd60958f5098e76de270a933285c24dfdc6f": [
            "pod_name=demo-app-success-c485bc67b-klj45"
        ]
    }
    return tag_store.get(entity, [])


def test_report_pods_running(monkeypatch):
    check = KubeletCheck('kubelet', None, {}, [{}])
    monkeypatch.setattr(check, 'retrieve_pod_list', mock.Mock(return_value=json.loads(mock_from_file('pods.json'))))
    monkeypatch.setattr(check, 'gauge', mock.Mock())
    pod_list = check.retrieve_pod_list()

    with mock.patch("datadog_checks.kubelet.kubelet.get_tags", side_effect=mocked_get_tags):
        check._report_pods_running(pod_list, [])

    calls = [mock.call('kubernetes.pods.running', 1, ["pod_name:fluentd-gcp-v2.0.10-9q9t4"])]
    check.gauge.assert_has_calls(calls, any_order=True)


def test_report_container_spec_metrics(monkeypatch):
    check = KubeletCheck('kubelet', None, {}, [{}])
    monkeypatch.setattr(check, 'retrieve_pod_list', mock.Mock(return_value=json.loads(mock_from_file('pods.json'))))
    monkeypatch.setattr(check, 'gauge', mock.Mock())

    attrs = {'is_excluded.return_value': False}
    check.container_filter = mock.Mock(**attrs)

    pod_list = check.retrieve_pod_list()

    instance_tags = ["one:1", "two:2"]
    with mock.patch("datadog_checks.kubelet.kubelet.get_tags", side_effect=mocked_get_tags):
        check._report_container_spec_metrics(pod_list, instance_tags)

    calls = [
        mock.call('kubernetes.cpu.requests', 0.1, ['pod_name:fluentd-gcp-v2.0.10-9q9t4'] + instance_tags),
        mock.call('kubernetes.memory.requests', 209715200.0, ['pod_name:fluentd-gcp-v2.0.10-9q9t4'] + instance_tags),
        mock.call('kubernetes.memory.limits', 314572800.0, ['pod_name:fluentd-gcp-v2.0.10-9q9t4'] + instance_tags),
        mock.call('kubernetes.cpu.requests', 0.1, instance_tags),
        mock.call('kubernetes.cpu.requests', 0.1, instance_tags),
        mock.call('kubernetes.memory.requests', 134217728.0, instance_tags),
        mock.call('kubernetes.cpu.limits', 0.25, instance_tags),
        mock.call('kubernetes.memory.limits', 536870912.0, instance_tags),
        mock.call('kubernetes.cpu.requests', 0.1, ["pod_name=demo-app-success-c485bc67b-klj45"] + instance_tags),
    ]
    check.gauge.assert_has_calls(calls, any_order=True)


class MockResponse(mock.Mock):
    @staticmethod
    def iter_lines():
        return []


def test_perform_kubelet_check(monkeypatch):
    check = KubeletCheck('kubelet', None, {}, [{}])
    check.kube_health_url = "http://127.0.0.1:10255/healthz"
    check.kubelet_conn_info = {}
    monkeypatch.setattr(check, 'service_check', mock.Mock())

    instance_tags = ["one:1"]
    get = MockResponse()
    with mock.patch("requests.get", side_effect=get):
        check._perform_kubelet_check(instance_tags)

    get.assert_has_calls([
        mock.call('http://127.0.0.1:10255/healthz', cert=None, headers=None, params={'verbose': True}, timeout=10,
                  verify=None)])
    calls = [mock.call('kubernetes.kubelet.check', 0, tags=instance_tags)]
    check.service_check.assert_has_calls(calls)


def test_report_node_metrics(monkeypatch):
    check = KubeletCheck('kubelet', None, {}, [{}])
    monkeypatch.setattr(check, '_retrieve_node_spec', mock.Mock(return_value={'num_cores': 4, 'memory_capacity': 512}))
    monkeypatch.setattr(check, 'gauge', mock.Mock())
    check._report_node_metrics(['foo:bar'])
    calls = [
        mock.call('kubernetes.cpu.capacity', 4.0, ['foo:bar']),
        mock.call('kubernetes.memory.capacity', 512.0, ['foo:bar'])
    ]
    check.gauge.assert_has_calls(calls, any_order=False)
