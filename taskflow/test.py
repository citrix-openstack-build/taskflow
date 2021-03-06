# -*- coding: utf-8 -*-

#    Copyright (C) 2012 Yahoo! Inc. All Rights Reserved.
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

from testtools import compat
from testtools import matchers
from testtools import testcase

from taskflow import exceptions
from taskflow.tests import utils


class GreaterThanEqual(object):
    """Matches if the item is geq than the matchers reference object."""

    def __init__(self, source):
        self.source = source

    def match(self, other):
        if other >= self.source:
            return None
        return matchers.Mismatch("%s was not >= %s" % (other, self.source))


class FailureRegexpMatcher(object):
    """Matches if the failure was caused by the given exception and its string
    matches to the given pattern.
    """

    def __init__(self, exc_class, pattern):
        self.exc_class = exc_class
        self.pattern = pattern

    def match(self, failure):
        for cause in failure:
            if cause.check(self.exc_class) is not None:
                return matchers.MatchesRegex(
                    self.pattern).match(cause.exception_str)
        return matchers.Mismatch("The `%s` wasn't caused by the `%s`" %
                                 (failure, self.exc_class))


class TestCase(testcase.TestCase):
    """Test case base class for all taskflow unit tests."""

    def assertRaisesRegexp(self, exc_class, pattern, callable_obj,
                           *args, **kwargs):
        # TODO(harlowja): submit a pull/review request to testtools to add
        # this method to there codebase instead of having it exist in ours
        # since it really doesn't belong here.

        class ReRaiseOtherTypes(object):
            def match(self, matchee):
                if not issubclass(matchee[0], exc_class):
                    compat.reraise(*matchee)

        class CaptureMatchee(object):
            def match(self, matchee):
                self.matchee = matchee[1]

        capture = CaptureMatchee()
        matcher = matchers.Raises(matchers.MatchesAll(ReRaiseOtherTypes(),
                                  matchers.MatchesException(exc_class,
                                                            pattern),
                                  capture))
        our_callable = testcase.Nullary(callable_obj, *args, **kwargs)
        self.assertThat(our_callable, matcher)
        return capture.matchee

    def assertGreater(self, first, second):
        matcher = matchers.GreaterThan(first)
        self.assertThat(second, matcher)

    def assertGreaterEqual(self, first, second):
        matcher = GreaterThanEqual(first)
        self.assertThat(second, matcher)

    def assertRegexpMatches(self, text, pattern):
        matcher = matchers.MatchesRegex(pattern)
        self.assertThat(text, matcher)

    def assertIsSuperAndSubsequence(self, super_seq, sub_seq, msg=None):
        super_seq = list(super_seq)
        sub_seq = list(sub_seq)
        current_tail = super_seq
        for sub_elem in sub_seq:
            try:
                super_index = current_tail.index(sub_elem)
            except ValueError:
                # element not found
                if msg is None:
                    msg = ("%r is not subsequence of %r: "
                           "element %r not found in tail %r"
                           % (sub_seq, super_seq, sub_elem, current_tail))
                self.fail(msg)
            else:
                current_tail = current_tail[super_index + 1:]

    def assertFailuresRegexp(self, exc_class, pattern, callable_obj, *args,
                             **kwargs):
        """Assert that the callable failed with the given exception and its
        string matches to the given pattern.
        """
        try:
            with utils.wrap_all_failures():
                callable_obj(*args, **kwargs)
        except exceptions.WrappedFailure as e:
            self.assertThat(e, FailureRegexpMatcher(exc_class, pattern))


class MockTestCase(TestCase):

    def setUp(self):
        super(MockTestCase, self).setUp()
        self.master_mock = mock.Mock(name='master_mock')

    def _patch(self, target, autospec=True, **kwargs):
        """Patch target and attach it to the master mock."""
        patcher = mock.patch(target, autospec=autospec, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)

        attach_as = kwargs.pop('attach_as', None)
        if attach_as is not None:
            self.master_mock.attach_mock(mocked, attach_as)

        return mocked

    def _patch_class(self, module, name, autospec=True, attach_as=None):
        """Patch class, create class instance mock and attach them to
        the master mock.
        """
        if autospec:
            instance_mock = mock.Mock(spec_set=getattr(module, name))
        else:
            instance_mock = mock.Mock()

        patcher = mock.patch.object(module, name, autospec=autospec)
        class_mock = patcher.start()
        self.addCleanup(patcher.stop)
        class_mock.return_value = instance_mock

        if attach_as is None:
            attach_class_as = name
            attach_instance_as = name.lower()
        else:
            attach_class_as = attach_as + '_class'
            attach_instance_as = attach_as

        self.master_mock.attach_mock(class_mock, attach_class_as)
        self.master_mock.attach_mock(instance_mock, attach_instance_as)

        return class_mock, instance_mock

    def _reset_master_mock(self):
        self.master_mock.reset_mock()
