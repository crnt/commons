# ==================================================================================================
# Copyright 2011 Twitter, Inc.
# --------------------------------------------------------------------------------------------------
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this work except in compliance with the License.
# You may obtain a copy of the License in the LICENSE file, or at:
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==================================================================================================

from collections import deque
from copy import copy

from twitter.common.collections import OrderedSet
from twitter.pants import is_apt, is_java, is_scala
from twitter.pants.targets import JavaLibrary, ScalaLibrary

import bang

def extract_target(java_targets, is_transitive, name = None):
  meta_target = bang.extract_target(java_targets, name)

  internal_deps, jar_deps = _extract_target(meta_target,
                                            is_transitive,
                                            lambda target: is_apt(target))

  # TODO(John Sirois): make an empty source set work in ant/compile.xml
  sources = [ '__no_source__' ]

  all_deps = OrderedSet()
  all_deps.update(internal_deps)
  all_deps.update(jar_deps)

  if is_java(meta_target):
    return JavaLibrary('ide',
                       sources,
                       dependencies = all_deps,
                       excludes = meta_target.excludes,
                       is_meta = True)
  elif is_scala(meta_target):
    return ScalaLibrary('ide',
                        sources,
                        dependencies = all_deps,
                        excludes = meta_target.excludes,
                        is_meta = True)
  else:
    raise TypeError("Cannot generate IDE configuration for targets: %s" % java_targets)

def _extract_target(meta_target, is_transitive, is_apt):
  """
    Extracts the minimal set of internal dependencies and external jar dependencies from the given
    (meta) target so that an ide can run any required custom annotation processors and resolve all
    symbols.

    The extraction algorithm proceeds under the following assumptions:
    1.) A custom annotation processor (or even a codegen target) may have internal dependencies
    2.) An IDE need not have any compiled classes for ide compilable sources on its classpath in
        order to resolve symbols, it just needs any custom annotation processors, custom codegen'ed
        classes and any external jars dependencies

    The algorithm then proceeds to categorize each target as either ide classpath required target
    or not.  If the target is required on the ide classpath, it is retained and grafted into the
    graph of internal dependencies returned.  If not, the target's jar dependencies are added to the
    set of all external jar dependencies required on the ide classpath.  Finally the tuple of all
    collected (internal dependencies, jar dependencies) is returned.

    The assumptions noted above imply that any internal target dependended on by an ide classpath
    required target must also be grafted into the graph of internal dependencies returned.
  """

  class RootNode(object):
    def __init__(self):
      self.internal_dependencies = OrderedSet()

  root_target = RootNode()

  codegen_graph = deque([])
  codegen_graph.appendleft(root_target)
  jar_deps = OrderedSet()

  visited = set()
  def sift_targets(target, add_deps = False):
    if target not in visited:
      visited.add(target)
      is_needed_on_ide_classpath = add_deps or target.is_codegen or is_apt(target)

      if is_needed_on_ide_classpath:
        codegen_graph[0].internal_dependencies.add(target)
      else:
        for jar_dependency in target.jar_dependencies:
          if jar_dependency.rev:
            if is_transitive(target):
              jar_deps.add(jar_dependency)
            else:
              jar_deps.add(copy(jar_dependency).intransitive())

      if is_needed_on_ide_classpath:
        codegen_graph.appendleft(target)

      for internal_target in list(target.internal_dependencies):
        target.internal_dependencies.discard(internal_target)
        sift_targets(internal_target, is_needed_on_ide_classpath)

      if is_needed_on_ide_classpath:
        codegen_graph.popleft()

  sift_targets(meta_target)

  assert len(codegen_graph) == 1 and codegen_graph[0] == root_target,\
    "Unexpected walk: %s" % codegen_graph

  return codegen_graph.popleft().internal_dependencies, jar_deps
