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

import mock

from taskflow.engines.worker_based import engine
from taskflow.patterns import linear_flow as lf
from taskflow import test
from taskflow.tests import utils
from taskflow.utils import persistence_utils as pu


class TestWorkerBasedActionEngine(test.MockTestCase):

    def setUp(self):
        super(TestWorkerBasedActionEngine, self).setUp()
        self.broker_url = 'test-url'
        self.exchange = 'test-exchange'
        self.workers_info = {'test-topic': ['task1', 'task2']}

        # patch classes
        self.executor_mock, self.executor_inst_mock = self._patch_class(
            engine.executor, 'WorkerTaskExecutor', attach_as='executor')

    def test_creation_default(self):
        flow = lf.Flow('test-flow').add(utils.DummyTask())
        _, flow_detail = pu.temporary_flow_detail()
        engine.WorkerBasedActionEngine(flow, flow_detail, None, {}).compile()

        expected_calls = [
            mock.call.executor_class(uuid=flow_detail.uuid,
                                     url=None,
                                     exchange='default',
                                     workers_info={},
                                     transport=None,
                                     transport_options=None)
        ]
        self.assertEqual(self.master_mock.mock_calls, expected_calls)

    def test_creation_custom(self):
        flow = lf.Flow('test-flow').add(utils.DummyTask())
        _, flow_detail = pu.temporary_flow_detail()
        config = {'url': self.broker_url, 'exchange': self.exchange,
                  'workers_info': self.workers_info, 'transport': 'memory',
                  'transport_options': {}}
        engine.WorkerBasedActionEngine(
            flow, flow_detail, None, config).compile()

        expected_calls = [
            mock.call.executor_class(uuid=flow_detail.uuid,
                                     url=self.broker_url,
                                     exchange=self.exchange,
                                     workers_info=self.workers_info,
                                     transport='memory',
                                     transport_options={})
        ]
        self.assertEqual(self.master_mock.mock_calls, expected_calls)
