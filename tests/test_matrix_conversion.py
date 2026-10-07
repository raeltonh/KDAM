import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import app
from streamlit.testing.v1 import AppTest


class MatrixConversionTests(unittest.TestCase):
    def test_numeric_editor_and_spray_rules(self):
        rows = [{'Default setup': 'Dark cotton', 'Default spray': '65', 'Files': 1}]
        rules = app.build_spray_rule_rows(rows, preserve_source=True)
        self.assertEqual(rules[0]['Spray mode'], app.SPRAY_MODE_SOURCE)
        self.assertEqual(app.build_spray_rules(rules), {'dark cotton': ''})
        self.assertEqual(app.spray_rule_editor_data(rules)['Custom spray'].dtype.kind, 'f')
        for value in (0, 60, 65.5):
            custom = dict(rules[0], **{'Spray mode': app.SPRAY_MODE_CUSTOM, 'Custom spray': value})
            amount = next(iter(app.build_spray_rules([custom]).values()))
            root = ET.fromstring('<Root><SprayAmount>12</SprayAmount></Root>')
            app.apply_batch_spray_override(root, {'target_spray_amount': amount})
            self.assertEqual(float(app.get_text(root, 'SprayAmount')), value)
        at = AppTest.from_string('''import streamlit as st
from app import build_spray_rule_rows, spray_rule_editor_data
rows = build_spray_rule_rows([{"Default setup":"Dark", "Default spray":"65", "Files":1}])
st.data_editor(spray_rule_editor_data(rows), column_config={"Custom spray":st.column_config.NumberColumn("Custom spray",min_value=0.0,step=1.0)})
''').run()
        self.assertFalse(at.exception)

    def test_matrix_options_include_rss_sizes(self):
        with patch.object(app, 'load_mapping_rows', return_value=(None, [])), patch.object(app, 'load_icc_option_rows', return_value={}), patch.object(app, 'load_pallet_mapping_rows', return_value=[]):
            options = app.batch_target_options({'direction': 'plus_to_matrix'}, [])['pallet']
        for size in set(app.MATRIX_RSS_PALLET_MAP.values()):
            self.assertIn(size, options)

    def test_rss_conversion_uses_source_size_and_preserves_spray(self):
        source = ET.parse(app.APP_ROOT / 'templates/approved_atlas_max_template.ksf').getroot()
        template = ET.parse(app.APP_ROOT / 'templates/approved_matrix_template.ksf')
        app.replace_simple_text(source, 'SprayAmount', '60')
        for pallet, expected in app.MATRIX_RSS_PALLET_MAP.items():
            if 'MATRIX' in pallet:
                continue  # This alias belongs to Matrix input, not Plus input.
            with self.subTest(pallet=pallet):
                app.replace_simple_text(source, 'TableName', pallet)
                with patch.object(app, 'find_mapping_row', return_value=None), patch.object(app, 'apply_pallet_output_format'):
                    out = app.build_converted_root_cross(source, template, 'plus_to_matrix', 'template', 'template', 'source-file', 'test', 0, 0, None, 0, matrix_pallet_mode=app.MATRIX_PALLET_MODE_RSS)
                self.assertEqual(app.get_text(out, 'TableName'), expected)
                self.assertEqual(app.get_text(out, 'SprayAmount'), '60')


if __name__ == '__main__':
    unittest.main()
