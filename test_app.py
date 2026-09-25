import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree
from app import (new_exam, validate_exam, calculate, atomic_json, SUBJECTS, default_data_dir,
                 expired_subjects, read_cells, read_answer_keys, read_exam_id, write_xlsx, xlsx_path)


def type_answer_key(path, subject_index, row, value):
    """Simulate typing a correct answer into column C, as a user would in Excel."""
    sheet = f'xl/worksheets/sheet{subject_index + 1}.xml'
    with zipfile.ZipFile(path) as z:
        files = {name: z.read(name) for name in z.namelist()}
    files[sheet] = files[sheet].replace(f'<c r="C{row}"/>'.encode(), f'<c r="C{row}"><v>{value}</v></c>'.encode())
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)


class Tests(unittest.TestCase):
    def test_roundtrip_and_xlsx(self):
        e = new_exam()
        e['title'] = '모의고사:/?'
        e['round'] = '01'
        for s in range(5):
            e['answers'][s] = [i % 6 for i in range(20)]
            e['notes'][s] = f'{SUBJECTS[s]} 메모\n둘째 줄'
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            atomic_json(p/'draft.json', e)
            self.assertEqual(validate_exam(json.loads((p/'draft.json').read_text(encoding='utf-8'))), e)
            path = xlsx_path(p, e)
            self.assertEqual(path.name, '모의고사____01.xlsx')
            write_xlsx(path, e)
            cells = read_cells(path)
            self.assertEqual(list(cells), list(SUBJECTS))
            for s, subject in enumerate(SUBJECTS):
                values = cells[subject]
                self.assertEqual([values.get(f'B{r}', '') for r in range(2, 22)],
                                 [str(v) if v else '' for v in e['answers'][s]])
                self.assertEqual(values['B27'], f'{subject} 메모\n둘째 줄')
                self.assertEqual(values['B29'], '모의고사:/?')
                self.assertEqual(values['B30'], '01')
                self.assertEqual(values['B26'], '아니요')
            self.assertEqual(read_exam_id(cells), e['id'])
            with zipfile.ZipFile(path) as z:
                sheet = z.read('xl/worksheets/sheet1.xml').decode()
            # Round "01" stays text so Excel keeps the leading zero; answers are numbers.
            self.assertIn('<c r="B30" t="inlineStr"><is><t xml:space="preserve">01</t>', sheet)
            self.assertIn('<c r="B3"><v>1</v></c>', sheet)

    def test_answer_keys_kept_and_atomic_replace(self):
        e = new_exam(); e['title'] = '시험'; e['round'] = '1'
        with tempfile.TemporaryDirectory() as d:
            path = write_xlsx(xlsx_path(Path(d), e), e)
            type_answer_key(path, 0, 2, 3)
            e['answers'][0][0] = 3
            with patch('app.os.replace', side_effect=OSError('locked file')):
                original = path.read_bytes()
                with self.assertRaises(OSError): write_xlsx(path, e)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(d).glob('*.tmp')), [])
            write_xlsx(path, e)
            cells = read_cells(path)
            self.assertEqual(read_answer_keys(cells)['언어이해'], {2: '3'})
            self.assertEqual(cells['언어이해']['B2'], '3')
            with zipfile.ZipFile(path) as z:
                self.assertIn('<c r="C2"><v>3</v></c>', z.read('xl/worksheets/sheet1.xml').decode())

    def test_same_title_round_file_choice(self):
        e = new_exam(); e['title'] = '시험/A'; e['round'] = '1'
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            first = write_xlsx(xlsx_path(folder, e), e)
            self.assertEqual(xlsx_path(folder, e), first)  # the same exam rewrites its file
            other = new_exam(); other['title'] = '시험/A'; other['round'] = '1'
            second = write_xlsx(xlsx_path(folder, other), other)
            self.assertEqual(second.name, '시험_A_1_2.xlsx')
            self.assertEqual(xlsx_path(folder, e), first)
            self.assertEqual(xlsx_path(folder, other), second)
            # Files that are not readable answer workbooks are never overwritten.
            third = new_exam(); third['title'] = 'B'; third['round'] = ''
            (folder / 'B_회차미입력.xlsx').write_bytes(b'not a zip')
            with zipfile.ZipFile(folder / 'B_회차미입력_2.xlsx', 'w') as z:
                z.writestr('xl/workbook.xml', '<workbook/>')
            self.assertEqual(xlsx_path(folder, third).name, 'B_회차미입력_3.xlsx')

    def test_timer_record_and_unsafe_text(self):
        e = new_exam(); e['title'] = '제목\x0b'; e['round'] = '1'
        e['notes'][1] = 'a\x00b\x1fc\ud800d'
        e['timed_out'] = [1, 7, True, '2']
        self.assertEqual(expired_subjects({'expired': [4, 4, 0, -1, None]}), [0, 4])
        self.assertEqual(expired_subjects(new_exam()), [])
        with tempfile.TemporaryDirectory() as d:
            path = write_xlsx(Path(d) / 'x.xlsx', e)
            with zipfile.ZipFile(path) as z:
                for name in z.namelist():
                    if name.endswith('.xml') or name.endswith('.rels'):
                        ElementTree.fromstring(z.read(name))
            cells = read_cells(path)
            self.assertEqual(cells['자료해석']['B27'], 'abcd')
            self.assertEqual(cells['자료해석']['B26'], '예')
            self.assertEqual(cells['언어이해']['B26'], '아니요')

    def test_data_dir(self):
        self.assertEqual(default_data_dir('darwin'), Path.home() / 'Library' / 'Application Support' / 'AptitudeCompanion')
        with patch.dict('os.environ', {'LOCALAPPDATA': str(Path('C:/Users/u/AppData/Local'))}):
            self.assertEqual(default_data_dir('win32'), Path('C:/Users/u/AppData/Local') / 'AptitudeCompanion')

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
