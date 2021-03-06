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
import socket
import threading

from amqp import exceptions as amqp_exc

from taskflow.engines.worker_based import proxy
from taskflow import test


class TestProxy(test.MockTestCase):

    def setUp(self):
        super(TestProxy, self).setUp()
        self.uuid = 'test-uuid'
        self.broker_url = 'test-url'
        self.exchange_name = 'test-exchange'
        self.timeout = 5
        self.queue_arguments = {
            'x-expires': proxy.pr.QUEUE_EXPIRE_TIMEOUT * 1000
        }
        self.de_period = proxy.DRAIN_EVENTS_PERIOD

        # patch classes
        self.conn_mock, self.conn_inst_mock = self._patch_class(
            proxy.kombu, 'Connection')
        self.exchange_mock, self.exchange_inst_mock = self._patch_class(
            proxy.kombu, 'Exchange')
        self.queue_mock, self.queue_inst_mock = self._patch_class(
            proxy.kombu, 'Queue')
        self.producer_mock, self.producer_inst_mock = self._patch_class(
            proxy.kombu, 'Producer')

        # connection mocking
        self.conn_inst_mock.drain_events.side_effect = [
            socket.timeout, socket.timeout, KeyboardInterrupt]

        # connections mocking
        self.connections_mock = self._patch(
            "taskflow.engines.worker_based.proxy.kombu.connections",
            attach_as='connections')
        self.connections_mock.__getitem__().acquire().__enter__.return_value =\
            self.conn_inst_mock

        # producers mocking
        self.producers_mock = self._patch(
            "taskflow.engines.worker_based.proxy.kombu.producers",
            attach_as='producers')
        self.producers_mock.__getitem__().acquire().__enter__.return_value =\
            self.producer_inst_mock

        # consumer mocking
        self.conn_inst_mock.Consumer.return_value.__enter__ = mock.MagicMock()
        self.conn_inst_mock.Consumer.return_value.__exit__ = mock.MagicMock()

        # other mocking
        self.on_message_mock = mock.MagicMock(name='on_message')
        self.on_wait_mock = mock.MagicMock(name='on_wait')
        self.master_mock.attach_mock(self.on_wait_mock, 'on_wait')

        # reset master mock
        self._reset_master_mock()

    def _queue_name(self, uuid):
        return "%s_%s" % (self.exchange_name, uuid)

    def proxy_start_calls(self, calls, exc_type=mock.ANY):
        return [
            mock.call.Queue(name=self._queue_name(self.uuid),
                            exchange=self.exchange_inst_mock,
                            routing_key=self.uuid,
                            durable=False,
                            queue_arguments=self.queue_arguments,
                            channel=self.conn_inst_mock),
            mock.call.connection.Consumer(queues=self.queue_inst_mock,
                                          callbacks=[self.on_message_mock]),
            mock.call.connection.Consumer().__enter__(),
        ] + calls + [
            mock.call.connection.Consumer().__exit__(exc_type, mock.ANY,
                                                     mock.ANY),
            mock.ANY,
            mock.call.queue.delete(if_unused=True)
        ]

    def proxy(self, reset_master_mock=False, **kwargs):
        proxy_kwargs = dict(uuid=self.uuid,
                            exchange_name=self.exchange_name,
                            on_message=self.on_message_mock,
                            url=self.broker_url)
        proxy_kwargs.update(kwargs)
        p = proxy.Proxy(**proxy_kwargs)
        if reset_master_mock:
            self._reset_master_mock()
        return p

    def test_creation(self):
        self.proxy()

        master_mock_calls = [
            mock.call.Connection(self.broker_url, transport=None,
                                 transport_options=None),
            mock.call.Exchange(name=self.exchange_name,
                               channel=self.conn_inst_mock,
                               durable=False,
                               auto_delete=True)
        ]
        self.assertEqual(self.master_mock.mock_calls, master_mock_calls)

    def test_creation_custom(self):
        transport_opts = {'context': 'context'}
        self.proxy(transport='memory', transport_options=transport_opts)

        master_mock_calls = [
            mock.call.Connection(self.broker_url, transport='memory',
                                 transport_options=transport_opts),
            mock.call.Exchange(name=self.exchange_name,
                               channel=self.conn_inst_mock,
                               durable=False,
                               auto_delete=True)
        ]
        self.assertEqual(self.master_mock.mock_calls, master_mock_calls)

    def test_publish(self):
        task_data = 'task-data'
        task_uuid = 'task-uuid'
        routing_key = 'routing-key'
        kwargs = dict(a='a', b='b')

        self.proxy(reset_master_mock=True).publish(
            task_data, task_uuid, routing_key, **kwargs)

        master_mock_calls = [
            mock.call.Queue(name=self._queue_name(routing_key),
                            exchange=self.exchange_inst_mock,
                            routing_key=routing_key,
                            durable=False,
                            queue_arguments=self.queue_arguments),
            mock.call.producer.publish(body=task_data,
                                       routing_key=routing_key,
                                       exchange=self.exchange_inst_mock,
                                       correlation_id=task_uuid,
                                       declare=[self.queue_inst_mock],
                                       **kwargs)
        ]
        self.master_mock.assert_has_calls(master_mock_calls)

    def test_start(self):
        try:
            # KeyboardInterrupt will be raised after two iterations
            self.proxy(reset_master_mock=True).start()
        except KeyboardInterrupt:
            pass

        master_calls = self.proxy_start_calls([
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.connection.drain_events(timeout=self.de_period),
        ], exc_type=KeyboardInterrupt)
        self.master_mock.assert_has_calls(master_calls)

    def test_start_with_on_wait(self):
        try:
            # KeyboardInterrupt will be raised after two iterations
            self.proxy(reset_master_mock=True,
                       on_wait=self.on_wait_mock).start()
        except KeyboardInterrupt:
            pass

        master_calls = self.proxy_start_calls([
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.on_wait(),
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.on_wait(),
            mock.call.connection.drain_events(timeout=self.de_period),
        ], exc_type=KeyboardInterrupt)
        self.master_mock.assert_has_calls(master_calls)

    def test_start_with_on_wait_raises(self):
        self.on_wait_mock.side_effect = RuntimeError('Woot!')
        try:
            # KeyboardInterrupt will be raised after two iterations
            self.proxy(reset_master_mock=True,
                       on_wait=self.on_wait_mock).start()
        except KeyboardInterrupt:
            pass

        master_calls = self.proxy_start_calls([
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.on_wait(),
        ], exc_type=RuntimeError)
        self.master_mock.assert_has_calls(master_calls)

    def test_start_queue_delete_not_found(self):
        self.queue_inst_mock.delete.side_effect = amqp_exc.NotFound('Woot!')
        try:
            # KeyboardInterrupt will be raised after two iterations
            self.proxy(reset_master_mock=True).start()
        except KeyboardInterrupt:
            pass

        master_calls = self.proxy_start_calls([
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.connection.drain_events(timeout=self.de_period),
        ], exc_type=KeyboardInterrupt)
        self.master_mock.assert_has_calls(master_calls)

    @mock.patch("taskflow.engines.worker_based.proxy.LOG.error")
    def test_start_queue_delete_raises(self, mocked_error):
        self.queue_inst_mock.delete.side_effect = RuntimeError('Woot!')
        try:
            # KeyboardInterrupt will be raised after two iterations
            self.proxy(reset_master_mock=True).start()
        except KeyboardInterrupt:
            pass

        master_calls = self.proxy_start_calls([
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.connection.drain_events(timeout=self.de_period),
        ], exc_type=KeyboardInterrupt)
        self.master_mock.assert_has_calls(master_calls)
        self.assertTrue(mocked_error.called)

    def test_start_exchange_delete_not_found(self):
        self.exchange_inst_mock.delete.side_effect = amqp_exc.NotFound('Woot!')
        try:
            # KeyboardInterrupt will be raised after two iterations
            self.proxy(reset_master_mock=True).start()
        except KeyboardInterrupt:
            pass

        master_calls = self.proxy_start_calls([
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.connection.drain_events(timeout=self.de_period),
        ], exc_type=KeyboardInterrupt)
        self.master_mock.assert_has_calls(master_calls)

    @mock.patch("taskflow.engines.worker_based.proxy.LOG.error")
    def test_start_exchange_delete_raises(self, mocked_error):
        self.exchange_inst_mock.delete.side_effect = RuntimeError('Woot!')
        try:
            # KeyboardInterrupt will be raised after two iterations
            self.proxy(reset_master_mock=True).start()
        except KeyboardInterrupt:
            pass

        master_calls = self.proxy_start_calls([
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.connection.drain_events(timeout=self.de_period),
            mock.call.connection.drain_events(timeout=self.de_period),
        ], exc_type=KeyboardInterrupt)
        self.master_mock.assert_has_calls(master_calls)
        self.assertTrue(mocked_error.called)

    def test_stop(self):
        self.conn_inst_mock.drain_events.side_effect = socket.timeout

        # create proxy
        pr = self.proxy(reset_master_mock=True)

        # check that proxy is not running yes
        self.assertFalse(pr.is_running)

        # start proxy in separate thread
        t = threading.Thread(target=pr.start)
        t.daemon = True
        t.start()

        # make sure proxy is started
        pr.wait()

        # check that proxy is running now
        self.assertTrue(pr.is_running)

        # stop proxy and wait for thread to finish
        pr.stop()

        # wait for thread to finish
        t.join()

        self.assertFalse(pr.is_running)
