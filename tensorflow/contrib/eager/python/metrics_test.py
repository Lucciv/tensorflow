# Copyright 2017 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for Metrics."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import tempfile

from tensorflow.contrib.eager.python import metrics
from tensorflow.contrib.summary import summary_ops
from tensorflow.core.util import event_pb2
from tensorflow.python.eager import context
from tensorflow.python.eager import test
from tensorflow.python.framework import dtypes
from tensorflow.python.lib.io import tf_record
from tensorflow.python.ops import array_ops
from tensorflow.python.platform import gfile
from tensorflow.python.training import training_util


class MetricsTest(test.TestCase):

  def testMean(self):
    m = metrics.Mean()
    m([1, 10, 100])
    m(1000)
    m([10000.0, 100000.0])
    self.assertEqual(111111.0/6, m.result().numpy())
    self.assertEqual(dtypes.float64, m.dtype)
    self.assertEqual(dtypes.float64, m.result().dtype)

  def testInitVariables(self):
    m = metrics.Mean()
    m([1, 10, 100, 1000])
    m([10000.0, 100000.0])
    self.assertEqual(111111.0/6, m.result().numpy())
    m.init_variables()
    m(7)
    self.assertEqual(7.0, m.result().numpy())

  def testWriteSummaries(self):
    m = metrics.Mean()
    m([1, 10, 100])
    training_util.get_or_create_global_step()
    logdir = tempfile.mkdtemp()
    with summary_ops.create_summary_file_writer(
        logdir, max_queue=0,
        name="t0").as_default(), summary_ops.always_record_summaries():
      m.result()  # As a side-effect will write summaries.

    self.assertTrue(gfile.Exists(logdir))
    files = gfile.ListDirectory(logdir)
    self.assertEqual(len(files), 1)
    records = list(
        tf_record.tf_record_iterator(os.path.join(logdir, files[0])))
    self.assertEqual(len(records), 2)
    event = event_pb2.Event()
    event.ParseFromString(records[1])
    self.assertEqual(event.summary.value[0].simple_value, 37.0)

  def testWeightedMean(self):
    m = metrics.Mean()
    m([1, 100, 100000], weights=[1, 0.2, 0.3])
    m([500000, 5000, 500])  # weights of 1 each
    self.assertNear(535521/4.5, m.result().numpy(), 0.001)

  def testMeanDtype(self):
    # Can override default dtype of float64.
    m = metrics.Mean(dtype=dtypes.float32)
    m([0, 2])
    self.assertEqual(1, m.result().numpy())
    self.assertEqual(dtypes.float32, m.dtype)
    self.assertEqual(dtypes.float32, m.result().dtype)

  def testAccuracy(self):
    m = metrics.Accuracy()
    m([0, 1, 2, 3], [0, 0, 0, 0])  # 1 correct
    m([4], [4])  # 1 correct
    m([5], [0])  # 0 correct
    m([6], [6])  # 1 correct
    m([7], [2])  # 0 correct
    self.assertEqual(3.0/8, m.result().numpy())
    self.assertEqual(dtypes.float64, m.dtype)
    self.assertEqual(dtypes.float64, m.result().dtype)

  def testWeightedAccuracy(self):
    m = metrics.Accuracy()
    # 1 correct, total weight of 2
    m([0, 1, 2, 3], [0, 0, 0, 0], weights=[1, 1, 0, 0])
    m([4], [4], weights=[0.5])  # 1 correct with a weight of 0.5
    m([5], [0], weights=[0.5])  # 0 correct, weight 0.5
    m([6], [6])  # 1 correct, weight 1
    m([7], [2])  # 0 correct, weight 1
    self.assertEqual(2.5/5, m.result().numpy())

  def testAccuracyDtype(self):
    # Can override default dtype of float64.
    m = metrics.Accuracy(dtype=dtypes.float32)
    m([0, 0], [0, 1])
    self.assertEqual(0.5, m.result().numpy())
    self.assertEqual(dtypes.float32, m.dtype)
    self.assertEqual(dtypes.float32, m.result().dtype)

  def testTwoMeans(self):
    # Verify two metrics with the same class and name don't
    # accidentally share state.
    m1 = metrics.Mean()
    m1(0)
    with self.assertRaises(ValueError):
      m2 = metrics.Mean()
      m2(2)

  def testNamesWithSpaces(self):
    # Verify two metrics with the same class and name don't
    # accidentally share state.
    m1 = metrics.Mean("has space")
    m1(0)
    self.assertEqual(m1.name, "has space")
    self.assertEqual(m1.numer.name, "has_space/numer:0")

  def testGraph(self):
    with context.graph_mode(), self.test_session() as sess:
      m = metrics.Mean()
      p = array_ops.placeholder(dtypes.float32)
      accumulate = m(p)
      init_op = m.init_variables()
      init_op.run()
      sess.run(accumulate, feed_dict={p: [1, 10, 100]})
      sess.run(accumulate, feed_dict={p: 1000})
      sess.run(accumulate, feed_dict={p: [10000, 100000]})
      self.assertAllEqual(m.result().eval(), 111111.0/6)
      # Second init resets all the variables.
      init_op.run()
      sess.run(accumulate, feed_dict={p: 7})
      self.assertAllEqual(m.result().eval(), 7)

  def testTwoMeansGraph(self):
    # Verify two metrics with the same class and name don't
    # accidentally share state.
    with context.graph_mode():
      m1 = metrics.Mean()
      m1(0)
      with self.assertRaises(ValueError):
        m2 = metrics.Mean()
        m2(2)


if __name__ == "__main__":
  test.main()
