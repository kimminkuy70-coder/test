import tempfile
import unittest
from pathlib import Path
import json
from app import new_exam, validate_exam, export_exam, calculate, atomic_json, SUBJECTS

class Tests(unittest.TestCase):
    def test_roundtrip_and_export(self):
        e = new_exam()
        e['title'] = '모의고사:/?'
        e['round'] = '1회'
        for s in range(5):
            e['answers'][s] = [i % 6 for i in range(20)]
            e['notes'][s] = f'{SUBJECTS[s]} 메모\n둘째 줄'
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            atomic_json(p/'draft.json', e)
            self.assertEqual(validate_exam(json.loads((p/'draft.json').read_text())), e)
            a, b = export_exam(p, e), export_exam(p, e)
            self.assertNotEqual(a, b)
            text = a.read_text(encoding='utf-8-sig')
            import re
            self.assertEqual(len(re.findall(r'^\d{2} \|', text, re.M)), 100)
            self.assertEqual(text.count('01 | 미응답'), 5)
            self.assertEqual(text.count('20 | 1'), 5)
            self.assertTrue(all(subject in text for subject in SUBJECTS))
            self.assertIn('둘째 줄', text)
    def test_bad_draft(self):
        for value in (6, -1, True, '1'):
            e = new_exam(); e['answers'][0][0] = value
            with self.assertRaises(ValueError): validate_exam(e)
    def test_calculator(self):
        self.assertEqual(calculate('(2+3)×4÷2'), '10')
        self.assertEqual(calculate('-1.5 + .5'), '-1')
        for value in ('__import__("os")', '2**100', '[1]', 'True', '2//1'):
            with self.assertRaises(ValueError): calculate(value)
        with self.assertRaises(ZeroDivisionError): calculate('1/0')

if __name__ == '__main__': unittest.main()
