# -*- coding: utf-8 -*-

# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright (C) 2014 Yahoo! Inc. All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import inspect
import logging
import types

from concurrent import futures

import six

from taskflow.engines.worker_based import endpoint
from taskflow.engines.worker_based import server
from taskflow.openstack.common import importutils
from taskflow import task as t_task
from taskflow.utils import reflection
from taskflow.utils import threading_utils as tu

LOG = logging.getLogger(__name__)


class Worker(object):
    """Worker that can be started on a remote host for handling tasks requests.

    :param url: broker url
    :param exchange: broker exchange name
    :param topic: topic name under which worker is stated
    :param tasks: tasks list that worker is capable to perform

        Tasks list item can be one of the following types:
        1. String:

            1.1 Python module name:

                > tasks=['taskflow.tests.utils']

            1.2. Task class (BaseTask subclass) name:

                > tasks=['taskflow.test.utils.DummyTask']

        3. Python module:

            > from taskflow.tests import utils
            > tasks=[utils]

        4. Task class (BaseTask subclass):

            > from taskflow.tests import utils
            > tasks=[utils.DummyTask]

    :param executor: custom executor object that is used for processing
        requests in separate threads
    :keyword threads_count: threads count to be passed to the default executor
    :keyword transport: broker transport to be used (e.g. amqp, memory, etc.)
    :keyword transport_options: broker transport options
    """

    def __init__(self, exchange, topic, tasks, executor=None, **kwargs):
        self._topic = topic
        self._executor = executor
        self._threads_count = kwargs.pop('threads_count',
                                         tu.get_optimal_thread_count())
        if self._executor is None:
            self._executor = futures.ThreadPoolExecutor(self._threads_count)
        self._endpoints = self._derive_endpoints(tasks)
        self._server = server.Server(topic, exchange, self._executor,
                                     self._endpoints, **kwargs)

    @staticmethod
    def _derive_endpoints(tasks):
        """Derive endpoints from list of strings, classes or packages."""
        derived_tasks = set()
        for item in tasks:
            module = None
            if isinstance(item, six.string_types):
                try:
                    pkg, cls = item.split(':')
                except ValueError:
                    module = importutils.import_module(item)
                else:
                    obj = importutils.import_class('%s.%s' % (pkg, cls))
                    if not reflection.is_subclass(obj, t_task.BaseTask):
                        raise TypeError("Item %s is not a BaseTask subclass" %
                                        item)
                    derived_tasks.add(obj)
            elif isinstance(item, types.ModuleType):
                module = item
            elif reflection.is_subclass(item, t_task.BaseTask):
                derived_tasks.add(item)
            else:
                raise TypeError("Item %s unexpected type: %s" %
                                (item, type(item)))

            # derive tasks
            if module is not None:
                for name, obj in inspect.getmembers(module):
                    if reflection.is_subclass(obj, t_task.BaseTask):
                        derived_tasks.add(obj)

        return [endpoint.Endpoint(task) for task in derived_tasks]

    def run(self):
        """Run worker."""
        LOG.info("Starting the '%s' topic worker in %s threads." %
                 (self._topic, self._threads_count))
        LOG.info("Tasks list:")
        for endpoint in self._endpoints:
            LOG.info("|-- %s" % endpoint)
        self._server.start()

    def wait(self):
        """Wait until worker is started."""
        self._server.wait()

    def stop(self):
        """Stop worker."""
        self._server.stop()
