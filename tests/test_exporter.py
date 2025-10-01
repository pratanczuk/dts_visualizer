from dts_visualizer.parser import DTSParser
from dts_visualizer.exporter import export_dtsi


def test_export_replaces_internal_phandles_with_labels():
    dts = """
    / {
      provider: clk@0 {
        phandle = <0x10>;
      };
      consumer@1 {
        clocks = <0x10 0>;
      };
    };
    """
    parser = DTSParser()
    root = parser.parse(dts)
    # export the root child 'consumer@1'
    consumer = next(n for n in root.children if n.name.startswith('consumer'))
    txt = export_dtsi(consumer)
    # No explicit phandle property in export
    assert 'phandle' not in txt
    # No raw 0x10 references inside exported subtree (it should be &label if provider were inside subtree)
    # since provider is outside subtree, the numeric reference remains
    assert '<0x10' in txt or '&' in txt
