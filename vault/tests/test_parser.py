import pytest

from datadog_checks.vault.errors import UnknownMetric, UnknownTags
from datadog_checks.vault.metrics import METRIC_PREFIX, METRICS
from datadog_checks.vault.parser import parse_metric


class TestParseMetric:
    def test_unknown_metric(self):
        with pytest.raises(UnknownMetric):
            parse_metric('foo.bar')

    def test_unknown_tag(self):
        with pytest.raises(UnknownTags):
            parse_metric('stats.major.overflow')

    def test_runtime(self):
        metric = 'runtime.num_keys'
        tags = [tag for tags in METRICS[metric]['tags'] for tag in tags]

        assert parse_metric(metric) == (
            METRIC_PREFIX + metric,
            list(tags),
            METRICS[metric]['method']
        )

    def test_http_router_filter(self):
        metric = 'http{}.rq_total'
        untagged_metric = metric.format('')
        tags = [tag for tags in METRICS[untagged_metric]['tags'] for tag in tags]
        tag0 = 'some_stat_prefix'
        tagged_metric = metric.format('.{}'.format(tag0))

        assert parse_metric(tagged_metric) == (
            METRIC_PREFIX + untagged_metric,
            ['{}:{}'.format(tags[0], tag0)],
            METRICS[untagged_metric]['method']
        )

    def test_http_router_filter_vhost(self):
        metric = 'vhost{}.vcluster{}.upstream_rq_time'
        untagged_metric = metric.format('', '')
        tags = [tag for tags in METRICS[untagged_metric]['tags'] for tag in tags]
        tag0 = 'some_vhost_name'
        tag1 = 'some_vcluster_name'
        tagged_metric = metric.format('.{}'.format(tag0), '.{}'.format(tag1))

        assert parse_metric(tagged_metric) == (
            METRIC_PREFIX + untagged_metric,
            ['{}:{}'.format(tags[0], tag0), '{}:{}'.format(tags[1], tag1)],
            METRICS[untagged_metric]['method']
        )
