# -*- coding: utf-8 -*-

#    Copyright (C) 2013 Yahoo! Inc. All Rights Reserved.
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

import threading

from concurrent import futures

from taskflow.utils import eventlet_utils as eu

DONE_STATES = frozenset([
    futures._base.CANCELLED_AND_NOTIFIED,
    futures._base.FINISHED,
])


class _Waiter(object):
    """Provides the event that wait_for_any() blocks on."""
    def __init__(self, is_green):
        if is_green:
            assert eu.EVENTLET_AVAILABLE, ('eventlet is needed to use this'
                                           ' feature')
            self.event = eu.green_threading.Event()
        else:
            self.event = threading.Event()

    def add_result(self, future):
        self.event.set()

    def add_exception(self, future):
        self.event.set()

    def add_cancelled(self, future):
        self.event.set()


def _partition_futures(fs):
    """Partitions the input futures into done and not done lists."""
    done = []
    not_done = []
    for f in fs:
        if f._state in DONE_STATES:
            done.append(f)
        else:
            not_done.append(f)
    return (done, not_done)


def wait_for_any(fs, timeout=None):
    """Wait for one of the futures to complete.

    Works correctly with both green and non-green futures.
    Returns pair (done, not_done).
    """
    with futures._base._AcquireFutures(fs):
        (done, not_done) = _partition_futures(fs)
        if done:
            return (done, not_done)
        is_green = any(isinstance(f, eu.GreenFuture) for f in fs)
        waiter = _Waiter(is_green)
        for f in fs:
            f._waiters.append(waiter)

    waiter.event.wait(timeout)
    for f in fs:
        f._waiters.remove(waiter)

    with futures._base._AcquireFutures(fs):
        return _partition_futures(fs)


def make_completed_future(result):
    """Make with completed with given result."""
    future = futures.Future()
    future.set_result(result)
    return future
