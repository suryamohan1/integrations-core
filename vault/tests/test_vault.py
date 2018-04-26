# (C) Datadog, Inc. 2018
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
import os
import subprocess

import mock
import pytest
from datadog_checks.utils.common import get_docker_hostname

from datadog_checks.vault import Vault
from datadog_checks.vault.metrics import METRIC_PREFIX, METRICS

HERE = os.path.dirname(os.path.abspath(__file__))
DOCKER_DIR = os.path.join(HERE, 'docker')


@pytest.fixture
def aggregator():
    from datadog_checks.stubs import aggregator
    aggregator.reset()
    return aggregator


@pytest.fixture(scope='session', autouse=True)
def spin_up_vault():
    base_command = [
        'docker-compose', '-f', os.path.join(DOCKER_DIR, 'docker-compose.yaml')
    ]
    subprocess.check_call(base_command + ['up', '-d'])
    yield
    subprocess.check_call(base_command + ['down'])


class TestVault:
    CHECK_NAME = 'vault'
    INSTANCES = {
        'main': {
            'stats_url': 'http://{}:8200/stats'.format(get_docker_hostname()),
        },
    }

    def test_success(self, aggregator):
        instance = self.INSTANCES['main']
        c = Vault(self.CHECK_NAME, None, {}, [instance])
        c.check(instance)

        metrics_collected = 0
        for metric in METRICS.keys():
            metrics_collected += len(aggregator.metrics(METRIC_PREFIX + metric))

        assert metrics_collected >= 20
        assert aggregator.service_checks(Vault.SERVICE_CHECK_NAME)[0].status == Vault.OK
