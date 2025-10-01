import os
import textwrap
from dts_visualizer.bindings import load_bindings


def test_load_bindings_indexes_phandle_props(tmp_path):
    yaml_text = textwrap.dedent(
        """
        $id: example.yaml
        $schema: http://devicetree.org/meta-schemas/core.yaml#
        title: Example Device
        compatible:
          const: vendor,example
        properties:
          clocks:
            items:
              - $ref: /schemas/types.yaml#/definitions/phandle-array
        additionalProperties: true
        """
    )
    d = tmp_path / 'bindings'
    d.mkdir()
    (d / 'example.yaml').write_text(yaml_text, encoding='utf-8')
    idx = load_bindings(str(d))
    assert 'vendor,example' in idx.compat_to_phandle_props
    assert 'clocks' in idx.compat_to_phandle_props['vendor,example']
