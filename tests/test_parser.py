from dts_visualizer.parser import DTSParser


def test_parse_device_tree_smoke():
    # Ensure the sample DTS parses and yields a non-empty tree
    path = 'tests/device_tree.dts'
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        text = f.read()
    parser = DTSParser()
    root = parser.parse(text)
    assert root.path == '/'
    # has some children
    assert len(root.children) > 0
    # at least one node should have properties
    assert any(n.properties for n in root.children)
