"""Integration regressions: real inference and editable Word structures."""
import io
import re
import unittest
import zipfile
from pathlib import Path
from PIL import Image
from lxml import etree
from fastapi.testclient import TestClient
import app

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.load_engine()
        assert app.engine is not None, app.state
        cls.client = TestClient(app.app)

    def test_formula_images(self):
        expected = [r'x=\frac{-b\pm\sqrt{b^{2}-4ac}}{2a}', r'\int_{0}^{\infty}e^{-x}dx=1', r'e^{i\pi}+1=0']
        for i, tex in enumerate(expected):
            with self.subTest(example=i):
                data=(Path(__file__).parent/f'static/examples/{i}.png').read_bytes()
                r=self.client.post('/api/recognize',files={'file':('example.png',data,'image/png')})
                self.assertEqual(r.status_code,200,r.text)
                normalized = re.sub(r'\s+', '', re.sub(r'\\[!,;:]', '', r.json()['latex']))
                self.assertEqual(normalized,tex)
                word=self.client.post('/api/word',json={'latex':r.json()['latex']})
                self.assertEqual(word.status_code,200)

    def test_stacked_operator_normalization(self):
        from ocr_engine import normalize_latex
        source=r'\mathop { \operatorname* { m a x } } _ { j } |e_{ij}|'
        self.assertEqual(normalize_latex(source),r'\operatorname*{max} _ { j } |e_{ij}|')
        # Leave unrelated/custom operators and ordinary subscripts untouched.
        custom=r'\mathop{\operatorname*{custom}}_{j}'
        self.assertEqual(normalize_latex(custom),custom)

    def test_cache_and_bounded_inference(self):
        from unittest.mock import patch
        data=(Path(__file__).parent/'static/examples/2.png').read_bytes()
        app.engine.cache.clear()
        first=self.client.post('/api/recognize',files={'file':('formula.png',data,'image/png')})
        self.assertFalse(first.json()['cached'])
        second=self.client.post('/api/recognize',files={'file':('formula.png',data,'image/png')})
        self.assertTrue(second.json()['cached'])
        self.assertEqual(first.json()['latex'],second.json()['latex'])
        app.engine.cache.clear()
        with patch.object(app.engine,'time_limit',0):
            stopped=self.client.post('/api/recognize',files={'file':('formula.png',data,'image/png')})
        self.assertEqual(stopped.status_code,422)
        self.assertFalse(app.lock.locked())

    def test_editable_word_structure(self):
        ns={'m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
        formulas=[(r'\frac{a}{b}','f'),(r'\sqrt{x}','rad'),(r'\begin{pmatrix}a&b\\c&d\end{pmatrix}','m'),(r'\sum_{i=1}^n x_i','nary')]
        for tex, tag in formulas:
            with self.subTest(formula=tex):
                r=self.client.post('/api/word',json={'latex':tex})
                self.assertEqual(r.status_code,200)
                tree=etree.fromstring(zipfile.ZipFile(io.BytesIO(r.content)).read('word/document.xml'))
                self.assertEqual(len(tree.xpath('//m:oMath',namespaces=ns)),1)
                self.assertTrue(tree.xpath(f'//m:{tag}',namespaces=ns))

    def test_invalid_images(self):
        r=self.client.post('/api/recognize',files={'file':('bad.png',b'not image','image/png')})
        self.assertEqual(r.status_code,422)
        b=io.BytesIO();Image.new('RGB',(100,50),'white').save(b,format='PNG')
        r=self.client.post('/api/recognize',files={'file':('blank.png',b.getvalue(),'image/png')})
        self.assertEqual(r.status_code,422)

    def test_input_boundaries(self):
        self.assertEqual(self.client.post('/api/mathml',json={'latex':''}).status_code,422)
        self.assertEqual(self.client.post('/api/mathml',json={'latex':'x'*12001}).status_code,422)
        self.assertEqual(self.client.post('/api/mathml',json={'latex':'x'},headers={'Origin':'https://example.org'}).status_code,403)
        r=self.client.post('/api/mathml',json={'latex':r'\frac{x}{y}'})
        self.assertIn('<mfrac>',r.json()['mathml'])

if __name__ == '__main__':
    unittest.main(verbosity=2)
