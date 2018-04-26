# (C) Datadog, Inc. 2018
# All rights reserved
# Licensed under a 3-clause BSD style license (see LICENSE)
from .utils import make_metric_tree

METRIC_PREFIX = 'vault.'

METRICS = {
    '': {
        'tags': (
            (),
            (),
        ),
        'method': 'gauge',
    },
}

METRIC_TREE = make_metric_tree(METRICS)
