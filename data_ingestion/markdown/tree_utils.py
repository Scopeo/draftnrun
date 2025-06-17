import logging
from typing import Callable, Optional

from anytree import Node, RenderTree


LOGGER = logging.getLogger(__name__)


def node_as_string(node):
    return node.name


def are_trees_equal(tree1: Node, tree2: Node, node_as_str: Optional[Callable[[Node], str]] = None) -> bool:
    """
    Compare two trees for equality
    Args:
        tree1 (Node): The root of the first tree
        tree2 (Node): The root of the second tree
        node_as_str (Callable[[Node], str], optional): A function to convert a node to a string. Defaults to None.
    Returns:
        bool: True if the trees are equal, False otherwise
    """
    if node_as_str is None:
        node_as_str = node_as_string

    if tree1 is None and tree2 is None:
        LOGGER.debug("Both trees are None => Equal")
        return True

    if tree1 is None or tree2 is None:
        LOGGER.debug("One of the trees is None => Not Equal")
        return False

    if node_as_str(tree1) != node_as_str(tree2):
        LOGGER.debug(f"Node names are different: {node_as_str(tree1)=} != {node_as_str(tree2)=}")
        return False

    if len(tree1.children) != len(tree2.children):
        LOGGER.debug(f"Number of children is different: {len(tree1.children)=} != {len(tree2.children)=}")
        return False

    for child1, child2 in zip(tree1.children, tree2.children):
        if not are_trees_equal(child1, child2, node_as_str):
            LOGGER.debug("Child trees are not equal")
            LOGGER.debug(f"{child1=}\n{child2=}")
            return False

    LOGGER.debug("Trees are equal")
    return True


def tree_to_string(node: Node, node_as_str: Optional[Callable[[Node], str]] = None) -> str:
    """
    Convert the tree starting from the given node into a string representation.
    Args:
        node (Node): The root node of the tree
    Returns:
        str: The string representation of the tree
    """
    if node_as_str is None:
        node_as_str = node_as_string
    tree_str = ""
    for pre, _, node in RenderTree(node):
        tree_str += "%s%s\n" % (pre, node_as_str(node))
    return tree_str.rstrip()
