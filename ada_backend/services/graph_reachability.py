import logging

import networkx as nx

from ada_backend.database.models import GraphRunnerEdge
from ada_backend.schemas.pipeline.graph_schema import ComponentNodeDTO

LOGGER = logging.getLogger(__name__)


def find_reachable_nodes(
    component_nodes: list[ComponentNodeDTO],
    edges: list[GraphRunnerEdge],
    trigger_node_ids: set[str],
) -> set[str]:
    """Compute nodes reachable from trigger nodes using only original DB edges."""
    if not trigger_node_ids:
        LOGGER.warning("Graph has no trigger nodes -- no blocks will be executed")
        return set()

    preliminary_graph = nx.DiGraph()
    for node in component_nodes:
        preliminary_graph.add_node(str(node.id))
    for edge in edges:
        if edge.source_node_id:
            preliminary_graph.add_edge(str(edge.source_node_id), str(edge.target_node_id))

    reachable: set[str] = set()
    for trigger_id in trigger_node_ids:
        if trigger_id in preliminary_graph:
            reachable.add(trigger_id)
            reachable.update(nx.descendants(preliminary_graph, trigger_id))

    return reachable
