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

# Lint as: python3
"""Tests for Sinkhorn initializers."""

from functools import partial

import jax
import jax.numpy as jnp
import numpy as np
import pytest

from ott.core import initializers as init_lib
from ott.core import linear_problems
from ott.core.sinkhorn import sinkhorn
from ott.geometry import geometry, pointcloud


def create_sorting_problem(rng, n, epsilon=0.01, online=False):
  # define ot problem
  x_init = jnp.array([-1., 0, .22])
  y_init = jnp.array([0., 0, 1.1])
  x_rng, y_rng = jax.random.split(rng)

  x = jnp.concatenate([x_init, 10 + jnp.abs(jax.random.normal(x_rng, (n,)))])
  y = jnp.concatenate([y_init, 10 + jnp.abs(jax.random.normal(y_rng, (n,)))])

  x = jnp.sort(x)
  y = jnp.sort(y)

  n = len(x)
  m = len(y)
  a = jnp.ones(n) / n
  b = jnp.ones(m) / m

  batch_size = 3 if online else None
  geom = pointcloud.PointCloud(
      x.reshape(-1, 1),
      y.reshape(-1, 1),
      epsilon=epsilon,
      batch_size=batch_size
  )
  ot_problem = linear_problems.LinearProblem(geom=geom, a=a, b=b)

  return ot_problem


def create_ot_problem(rng, n, m, d, epsilon=0.01, online=False):
  # define ot problem
  x_rng, y_rng = jax.random.split(rng)

  mu_a = jnp.array([-1, 1]) * 5
  mu_b = jnp.array([0, 0])

  x = jax.random.normal(x_rng, (n, d)) + mu_a
  y = jax.random.normal(y_rng, (m, d)) + mu_b

  a = jnp.ones(n) / n
  b = jnp.ones(m) / m

  batch_size = 3 if online else None
  geom = pointcloud.PointCloud(x, y, epsilon=epsilon, batch_size=batch_size)

  ot_problem = linear_problems.LinearProblem(geom=geom, a=a, b=b)
  return ot_problem


# define sinkhorn functions
@partial(jax.jit, static_argnames=['lse_mode', 'vector_min'])
def run_sinkhorn_sort_init(
    x, y, a=None, b=None, epsilon=0.01, vector_min=True, lse_mode=True
):
  geom = pointcloud.PointCloud(x, y, epsilon=epsilon)
  sort_init = init_lib.SortingInitializer(vectorized_update=vector_min)
  out = sinkhorn(
      geom,
      a=a,
      b=b,
      jit=True,
      potential_initializer=sort_init,
      lse_mode=lse_mode
  )
  return out


@partial(jax.jit, static_argnames=['lse_mode'])
def run_sinkhorn(x, y, a=None, b=None, epsilon=0.01, lse_mode=True):
  geom = pointcloud.PointCloud(x, y, epsilon=epsilon)
  out = sinkhorn(geom, a=a, b=b, jit=True, lse_mode=lse_mode)
  return out


@partial(jax.jit, static_argnames=['lse_mode'])
def run_sinkhorn_gaus_init(x, y, a=None, b=None, epsilon=0.01, lse_mode=True):
  geom = pointcloud.PointCloud(x, y, epsilon=epsilon)
  out = sinkhorn(
      geom,
      a=a,
      b=b,
      jit=True,
      potential_initializer=init_lib.GaussianInitializer(),
      lse_mode=lse_mode
  )
  return out


@pytest.mark.fast
class TestInitializers:

  def test_init_pytree(self):

    @jax.jit
    def init_sort():
      init = init_lib.SortingInitializer()
      return init

    @jax.jit
    def init_gaus():
      init = init_lib.GaussianInitializer()
      return init

    init_gaus()
    init_sort()

  @pytest.mark.parametrize(
      "vector_min, lse_mode", [(True, True), (True, False), (False, True)]
  )
  def test_sorting_init(self, vector_min: bool, lse_mode: bool):
    """Tests sorting dual initializer."""
    rng = jax.random.PRNGKey(42)
    n = 500
    epsilon = 0.01

    ot_problem = create_sorting_problem(
        rng=rng, n=n, epsilon=epsilon, online=False
    )
    # run sinkhorn
    sink_out_base = run_sinkhorn(
        x=ot_problem.geom.x,
        y=ot_problem.geom.y,
        a=ot_problem.a,
        b=ot_problem.b,
        epsilon=epsilon
    )
    base_num_iter = jnp.sum(sink_out_base.errors > -1)

    sink_out_init = run_sinkhorn_sort_init(
        x=ot_problem.geom.x,
        y=ot_problem.geom.y,
        a=ot_problem.a,
        b=ot_problem.b,
        epsilon=epsilon,
        vector_min=vector_min,
        lse_mode=lse_mode
    )
    sort_num_iter = jnp.sum(sink_out_init.errors > -1)

    # check initializer is better or equal
    if lse_mode:
      assert base_num_iter >= sort_num_iter

  def test_sorting_init_online(self, rng: jnp.ndarray):
    n = 100
    epsilon = 0.01

    ot_problem = create_sorting_problem(
        rng=rng, n=n, epsilon=epsilon, online=True
    )
    sort_init = init_lib.SortingInitializer(vectorized_update=True)
    with pytest.raises(AssertionError, match=r"online"):
      sort_init.init_dual_a(ot_problem=ot_problem, lse_mode=True)

  def test_sorting_init_square_cost(self, rng: jnp.ndarray):
    n = 100
    m = 150
    d = 1
    epsilon = 0.01

    ot_problem = create_ot_problem(rng, n, m, d, epsilon=epsilon, online=False)
    sort_init = init_lib.SortingInitializer(vectorized_update=True)
    with pytest.raises(AssertionError, match=r"square"):
      sort_init.init_dual_a(ot_problem=ot_problem, lse_mode=True)

  def test_default_initializer(self, rng: jnp.ndarray):
    """Tests default initializer"""
    n = 200
    m = 200
    d = 2
    epsilon = 0.01

    ot_problem = create_ot_problem(rng, n, m, d, epsilon=epsilon, online=False)

    default_potential_a = init_lib.DefaultInitializer().init_dual_a(
        ot_problem=ot_problem, lse_mode=True
    )
    default_potential_b = init_lib.DefaultInitializer().init_dual_b(
        ot_problem=ot_problem, lse_mode=True
    )

    # check default is 0
    np.testing.assert_array_equal(0., default_potential_a)
    np.testing.assert_array_equal(0., default_potential_b)

  def test_gauss_pointcloud_geom(self, rng: jnp.ndarray):
    n = 200
    m = 200
    d = 2
    epsilon = 0.01

    ot_problem = create_ot_problem(rng, n, m, d, epsilon=epsilon, online=False)

    gaus_init = init_lib.GaussianInitializer()
    new_geom = geometry.Geometry(
        cost_matrix=ot_problem.geom.cost_matrix, epsilon=epsilon
    )
    ot_problem = linear_problems.LinearProblem(
        geom=new_geom, a=ot_problem.a, b=ot_problem.b
    )

    with pytest.raises(AssertionError, match=r"point cloud"):
      gaus_init.init_dual_a(ot_problem=ot_problem, lse_mode=True)

  @pytest.mark.parametrize('lse_mode', [True, False])
  def test_gauss_initializer(self, lse_mode, rng: jnp.ndarray):
    """Tests Gaussian initializer"""
    # definte ot problem
    n = 200
    m = 200
    d = 2
    epsilon = 0.01

    ot_problem = create_ot_problem(rng, n, m, d, epsilon=epsilon, online=False)

    # run sinkhorn
    sink_out = run_sinkhorn(
        x=ot_problem.geom.x,
        y=ot_problem.geom.y,
        a=ot_problem.a,
        b=ot_problem.b,
        epsilon=epsilon,
        lse_mode=lse_mode
    )
    base_num_iter = jnp.sum(sink_out.errors > -1)
    sink_out = run_sinkhorn_gaus_init(
        x=ot_problem.geom.x,
        y=ot_problem.geom.y,
        a=ot_problem.a,
        b=ot_problem.b,
        epsilon=epsilon,
        lse_mode=lse_mode
    )
    gaus_num_iter = jnp.sum(sink_out.errors > -1)

    # check initializer is better
    if lse_mode:
      assert base_num_iter >= gaus_num_iter