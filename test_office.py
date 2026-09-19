"""Regressions for information lost by WPS's Office-math importer."""
import io
import unittest
import zipfile

from fastapi.testclient import TestClient
from lxml import etree
import app

NS = {"m": "http://schemas.openxmlformats.org/officeDocument/2006/math"}


class OfficeExportTests(unittest.TestCase):
    def export(self, latex):
        response = TestClient(app.app).post('/api/word', json={'latex': latex})
        self.assertEqual(response.status_code, 200, response.text[:200])
        with zipfile.ZipFile(io.BytesIO(response.content)) as doc:
            return etree.fromstring(doc.read('word/document.xml'))

    def test_nested_superscripts_and_square_root(self):
        root = self.export(r'x=\frac{-b\pm\sqrt{b^2-4ac}}{2a}')
        self.assertEqual(root.xpath('//m:f/m:num//m:sSup/m:sup//m:t/text()', namespaces=NS), ['2'])
        self.assertEqual(root.xpath('//m:rad/m:radPr/m:degHide/@m:val', namespaces=NS), ['1'])
        self.assertFalse(root.xpath('//m:box', namespaces=NS))
        self.assertIn('±', ''.join(root.xpath('//m:t/text()', namespaces=NS)))

    def test_indexed_root_keeps_degree(self):
        root = self.export(r'\sqrt[3]{x}')
        self.assertEqual(root.xpath('//m:rad/m:deg//m:t/text()', namespaces=NS), ['3'])
        self.assertFalse(root.xpath('//m:degHide', namespaces=NS))

    def test_max_limits_and_subscripts(self):
        root = self.export(r'\operatorname*{max}_{j}|e_{ij}|')
        self.assertEqual(root.xpath('//m:limLow/m:e//m:t/text()', namespaces=NS), ['max'])
        self.assertEqual(root.xpath('//m:limLow/m:lim//m:t/text()', namespaces=NS), ['j'])
        self.assertEqual(root.xpath('//m:sSub/m:sub//m:t/text()', namespaces=NS), ['i', 'j'])

    def test_sums_and_matrices_preserve_structure(self):
        root = self.export(r'\sum_{i=1}^{n}x_i^2+\begin{pmatrix}a&b\\c&d\end{pmatrix}')
        self.assertEqual(root.xpath('//m:sSubSup/m:sup//m:t/text()', namespaces=NS), ['2'])
        self.assertTrue(root.xpath('//m:nary/m:sub', namespaces=NS))
        self.assertEqual(len(root.xpath('//m:m/m:mr', namespaces=NS)), 2)
        self.assertEqual(len(root.xpath('//m:m/m:mr/m:e', namespaces=NS)), 4)

    def test_absent_sum_limit_and_explicit_spacing(self):
        root = self.export(r'\sqrt{\frac{1}{6}\sum_j e_{ij}^2},\quad\operatorname*{max}_j|e_{ij}|')
        self.assertEqual(root.xpath('//m:naryPr/m:supHide/@m:val', namespaces=NS), ['1'])
        self.assertFalse(root.xpath('//m:naryPr/m:subHide', namespaces=NS))
        self.assertIn('\u2003', ''.join(root.xpath('//m:t/text()', namespaces=NS)))


if __name__ == '__main__':
    unittest.main()
