import pytest

from anytree import Node

from data_ingestion.markdown.tree_utils import are_trees_equal, tree_to_string


@pytest.fixture
def tree():
    root = Node(
        "root",
        children=[
            Node("child1", children=[Node("grandchild1", children=[Node("leaf1")])]),
            Node(
                "child2",
                children=[
                    Node("grandchild2", children=[Node("leaf2"), Node("leaf3")]),
                    Node("grandchild3", children=[Node("leaf4")]),
                ],
            ),
        ],
    )
    return root


def test_are_trees_equal(tree):
    # Tree 1 (same as example tree)
    root1 = tree

    # Tree 2 (identical to Tree 1)
    root2 = Node(
        "root",
        children=[
            Node("child1", children=[Node("grandchild1", children=[Node("leaf1")])]),
            Node(
                "child2",
                children=[
                    Node("grandchild2", children=[Node("leaf2"), Node("leaf3")]),
                    Node("grandchild3", children=[Node("leaf4")]),
                ],
            ),
        ],
    )

    assert are_trees_equal(root1, root2)

    # Tree 3 (different from Tree 1)
    root3 = Node(
        "root",
        children=[
            Node("child1", children=[Node("grandchild1", children=[Node("leaf1")])]),
            Node(
                "child2",
                children=[
                    Node("grandchild2", children=[Node("leaf2"), Node("leaf3")]),
                    Node("grandchild4", children=[Node("leaf4")]),  # Different grandchild name
                ],
            ),
        ],
    )

    assert not are_trees_equal(root1, root3)


def test_print_tree(tree):
    tree_as_string = tree_to_string(tree)

    expected_output = (
        "root\n"
        "├── child1\n"
        "│   └── grandchild1\n"
        "│       └── leaf1\n"
        "└── child2\n"
        "    ├── grandchild2\n"
        "    │   ├── leaf2\n"
        "    │   └── leaf3\n"
        "    └── grandchild3\n"
        "        └── leaf4"
    )

    assert tree_as_string == expected_output
