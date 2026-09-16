"""Offline aptitude exam companion. Python 3.10+, standard library only."""
import ast
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

SUBJECTS = ('언어이해', '자료해석', '창의수리', '언어추리', '수열추리')
DATA_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'AptitudeCompanion'


def new_exam():
    return {'id': str(uuid.uuid4()), 'title': '', 'round': '',
            'started': datetime.now().astimezone().isoformat(timespec='seconds'),
            'answers': [[0] * 20 for _ in SUBJECTS], 'notes': [''] * 5}


def validate_exam(exam):
    if not isinstance(exam, dict):
        raise ValueError('시험 데이터 형식 오류')
    for key in ('id', 'title', 'round', 'started'):
        if not isinstance(exam.get(key), str):
            raise ValueError('시험 정보 오류')
    answers = exam.get('answers')
    if not isinstance(answers, list) or len(answers) != 5:
        raise ValueError('과목 수 오류')
    if any(not isinstance(row, list) or len(row) != 20 or
           any(type(v) is not int or v not in range(6) for v in row) for row in answers):
        raise ValueError('답안 형식 오류')
    notes = exam.get('notes')
    if not isinstance(notes, list) or len(notes) != 5 or any(not isinstance(n, str) for n in notes):
        raise ValueError('메모 형식 오류')
    return exam


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='draft-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def render_txt(exam):
    validate_exam(exam)
    lines = ['인적성 시험 답안 | 양식 버전 1', f"시험 식별번호: {exam['id']}",
             f"시험 제목: {exam['title']}", f"회차: {exam['round'] or '미입력'}",
             f"응시 일시: {exam['started']}",
             f"저장 일시: {datetime.now().astimezone().isoformat(timespec='seconds')}",
             '전체 문항 수: 100', '', '[채점 결과 — 추후 기입]',
             '과목 | 정답 | 오답 | 미응답 | 확인 필요']
    lines += [f'{s} | ___ | ___ | ___ | ___' for s in SUBJECTS]
    lines += ['전체 | ___ | ___ | ___ | ___',
              '과목별 합계 20 / 전체 합계 100', '']
    for index, subject in enumerate(SUBJECTS):
        lines += [f'[{index + 1}. {subject} 답안]', '문항 | 내 답 | 정답(추후 기입) | 결과']
        lines += [f'{i:02d} | {v if v else "미응답"} | |' for i, v in enumerate(exam['answers'][index], 1)]
        lines += [f'[{subject} 메모]', exam['notes'][index], '']
    lines += ['[시험 후 복기]', '취약 유형:', '시간이 부족했던 과목:', '다음 시험에서 개선할 점:']
    return '\n'.join(lines) + '\n'


def matching_exports(folder, exam):
    """Match original header values, not sanitized filenames (which can collide)."""
    matches = []
    for path in folder.glob('*.txt'):
        if path.is_symlink():
            continue
        try:
            with path.open(encoding='utf-8-sig') as f:
                header = [f.readline().rstrip('\r\n') for _ in range(6)]
            if (header[0] == '인적성 시험 답안 | 양식 버전 1'
                    and header[2] == f"시험 제목: {exam['title']}"
                    and header[3] == f"회차: {exam['round'] or '미입력'}"):
                matches.append(path)
        except UnicodeError:
            continue  # Unrelated text files need not be UTF-8.
    return sorted(matches, key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)


def replace_export(path, exam):
    """Write fully before atomically replacing the explicitly confirmed file."""
    text = render_txt(exam)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='answer-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8-sig', newline='\n') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def export_exam(folder, exam):
    folder.mkdir(parents=True, exist_ok=True)
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', exam['title']).strip(' .')[:65] or '시험'
    round_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', exam['round']).strip(' .')[:25] or '회차미입력'
    stem = f'{title}_{round_name}_{datetime.now():%Y%m%d_%H%M%S}_답안'
    for i in range(10000):
        path = folder / f'{stem}{"_" + str(i) if i else ""}.txt'
        try:
            with path.open('x', encoding='utf-8-sig', newline='\n') as f:
                f.write(render_txt(exam))
            return path
        except FileExistsError:
            continue
    raise OSError('저장 파일명 생성 실패')


def calculate(expression):
    """Evaluate only finite arithmetic, never arbitrary Python."""
    expression = expression.replace('×', '*').replace('÷', '/').replace('−', '-')
    if not expression.strip() or len(expression) > 150:
        raise ValueError('식을 입력하세요 (최대 150자)')
    tree = ast.parse(expression, mode='eval')
    if len(list(ast.walk(tree))) > 100:
        raise ValueError('식이 너무 깁니다')
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            a, b = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): value = a + b
            elif isinstance(node.op, ast.Sub): value = a - b
            elif isinstance(node.op, ast.Mult): value = a * b
            else: value = a / b
        else:
            raise ValueError('사칙연산과 괄호만 사용할 수 있습니다')
        if abs(value) > 1e100 or not math.isfinite(value):
            raise ValueError('계산 범위를 초과했습니다')
        return value
    return format(visit(tree.body), '.12g')


class ScrollPanel(ttk.Frame):
    """Each pane owns its scroll area; shrinking cannot overlap adjacent panes."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg='#f5f7fb', width=1, height=1)
        bar = ttk.Scrollbar(self, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        self.canvas.pack(side='left', fill='both', expand=True)
        bar.pack(side='right', fill='y')
        self.body = ttk.Frame(self.canvas, padding=8)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.body.bind('<Configure>', lambda _: self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>', lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        # Bind per descendant, never hijack calculator entry or memo wheel globally.
        self.bind_wheels(self)

    def bind_wheels(self, widget):
        widget.bind('<MouseWheel>', self.wheel, add='+')
        widget.bind('<Button-4>', lambda _: self.canvas.yview_scroll(-3, 'units'), add='+')
        widget.bind('<Button-5>', lambda _: self.canvas.yview_scroll(3, 'units'), add='+')
        for child in widget.winfo_children():
            self.bind_wheels(child)

    def wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1), 'units')
        return 'break'


class App(tk.Tk):
    def __init__(self, data_dir=DATA_DIR):
        super().__init__()
        self.title('인적성 시험 도우미')
        self.data_dir = Path(data_dir)
        self.draft_path = self.data_dir / 'draft.json'
        self.settings_path = self.data_dir / 'settings.json'
        self.exam = new_exam()
        self.settings = {}
        self.load_warning = ''
        self.job = None
        self.current = 0
        try:
            if self.settings_path.exists():
                self.settings = json.loads(self.settings_path.read_text(encoding='utf-8'))
                if not isinstance(self.settings, dict): self.settings = {}
            if self.draft_path.exists():
                self.exam = validate_exam(json.loads(self.draft_path.read_text(encoding='utf-8')))
        except (ValueError, OSError) as exc:
            self.load_warning = f'이전 기록을 복원하지 못했습니다: {exc}'
            if self.draft_path.exists():
                try:
                    self.draft_path.rename(self.draft_path.with_name(f'draft-damaged-{uuid.uuid4().hex[:8]}.json'))
                except OSError:
                    pass
        self.folder = Path(self.settings.get('folder', str(Path.home() / 'Documents' / '인적성답안')))
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', font=('맑은 고딕', 10), background='#f5f7fb')
        style.configure('TButton', padding=(5, 5))
        style.configure('Title.TLabel', font=('맑은 고딕', 11, 'bold'), foreground='#17365d')
        style.configure('TRadiobutton', padding=(2, 5))
        self.minsize(360, 540)
        height = min(900, max(540, self.winfo_screenheight() - 100))
        self.geometry(f'410x{height}+{max(0, self.winfo_screenwidth()-430)}+30')
        # Each pane clips overflow into its own scroll area.
        self.panes = tk.PanedWindow(self, orient='vertical', sashwidth=9, sashrelief='raised',
                                    bg='#cad5e5', borderwidth=0, opaqueresize=True)
        self.panes.pack(fill='both', expand=True)
        self.omr = ScrollPanel(self.panes)
        self.calc = ScrollPanel(self.panes)
        self.memo = ttk.Frame(self.panes, padding=8)
        self.panes.add(self.omr, minsize=150, stretch='always', height=int(height * .53))
        self.panes.add(self.calc, minsize=105, stretch='always', height=int(height * .29))
        self.panes.add(self.memo, minsize=95, stretch='always')
        self.build_omr()
        self.build_calculator()
        self.build_memo()
        self.status = tk.StringVar(value='이전 응시 기록 복원 완료' if self.draft_path.exists() else '새 시험을 시작하세요')
        ttk.Label(self, textvariable=self.status, anchor='w', padding=(7, 4), wraplength=330).pack(fill='x')
        self.update_idletasks()
        # Derive minimum width from actual font/widget requests, not a fixed pixel guess.
        width_min = max(360, self.omr.body.winfo_reqwidth() + 26,
                        self.calc.body.winfo_reqwidth() + 26)
        scale = max(1.0, float(self.tk.call('tk', 'scaling')) / (96 / 72))
        self.pane_minimums = tuple(round(v * scale) for v in (150, 105, 95))
        for pane, minimum in zip((self.omr, self.calc, self.memo), self.pane_minimums):
            self.panes.paneconfigure(pane, minsize=minimum)
        height_min = max(540, sum(self.pane_minimums) + 90)
        self.minsize(width_min, height_min)
        width = max(410, width_min)
        height = max(height, height_min)
        self.geometry(f'{width}x{height}+{max(0, self.winfo_screenwidth()-width-20)}+30')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.restore_subject()
        self.title_var.trace_add('write', lambda *_: self.changed())
        self.round_var.trace_add('write', lambda *_: self.changed())
        if self.load_warning:
            self.after(100, lambda: messagebox.showwarning('복원 확인', self.load_warning))

    def build_omr(self):
        body = self.omr.body
        body.columnconfigure(0, weight=1)
        ttk.Label(body, text='01  답안지', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        self.top = tk.BooleanVar(value=False)
        ttk.Checkbutton(body, text='항상 위', variable=self.top,
                        command=lambda: self.attributes('-topmost', self.top.get())).grid(row=0, column=1)
        self.title_var = tk.StringVar(value=self.exam['title'])
        self.round_var = tk.StringVar(value=self.exam['round'])
        ttk.Label(body, text='시험 제목').grid(row=1, column=0, columnspan=2, sticky='w', pady=(7, 2))
        ttk.Entry(body, textvariable=self.title_var, width=12).grid(row=2, column=0, columnspan=2, sticky='ew')
        rr = ttk.Frame(body)
        rr.grid(row=3, column=0, columnspan=2, sticky='ew', pady=5)
        rr.columnconfigure(1, weight=1)
        ttk.Label(rr, text='회차  ').grid(row=0, column=0)
        ttk.Entry(rr, textvariable=self.round_var, width=8).grid(row=0, column=1, sticky='ew')
        ttk.Button(rr, text='새 시험', command=self.start_new).grid(row=0, column=2, padx=(6, 0))
        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky='ew')
        for c in range(2): buttons.columnconfigure(c, weight=1)
        for i, (label, fn) in enumerate((('답안 저장', self.save_txt), ('답안지 폴더 열기', self.open_folder),
                                         ('저장 위치 변경', self.choose_folder), ('채점 프롬프트 복사', self.copy_prompt))):
            ttk.Button(buttons, text=label, command=fn).grid(row=i//2, column=i%2, sticky='ew', padx=2, pady=2)
        self.subject_var = tk.StringVar(value=SUBJECTS[0])
        selector = ttk.Combobox(body, textvariable=self.subject_var, values=SUBJECTS, state='readonly', width=15)
        selector.grid(row=5, column=0, columnspan=2, sticky='ew', pady=(10, 4))
        selector.bind('<<ComboboxSelected>>', self.switch_subject)
        self.progress = tk.StringVar()
        ttk.Label(body, textvariable=self.progress).grid(row=6, column=0, columnspan=2, sticky='w')
        grid = ttk.Frame(body)
        grid.grid(row=7, column=0, columnspan=2, sticky='ew', pady=5)
        for c in range(1, 6): grid.columnconfigure(c, weight=1, uniform='choices')
        self.answer_vars = []
        for row in range(20):
            var = tk.IntVar()
            self.answer_vars.append(var)
            ttk.Label(grid, text=f'{row+1:02d}', width=3).grid(row=row, column=0, sticky='w')
            for choice in range(1, 6):
                ttk.Radiobutton(grid, text=str(choice), variable=var, value=choice,
                                command=self.answer_changed).grid(row=row, column=choice, sticky='ew')
            ttk.Button(grid, text='해제', width=4, command=lambda r=row: self.clear_answer(r)).grid(row=row, column=6, pady=1)
        self.omr.bind_wheels(self.omr.body)

    def build_calculator(self):
        b = self.calc.body
        b.columnconfigure(0, weight=1)
        ttk.Label(b, text='02  계산기', style='Title.TLabel').grid(row=0, column=0, sticky='w')
        self.expr = tk.StringVar()
        entry = ttk.Entry(b, textvariable=self.expr, justify='right', width=12, font=('맑은 고딕', 14))
        entry.grid(row=1, column=0, sticky='ew', pady=5)
        entry.bind('<Return>', lambda _: self.evaluate())
        entry.bind('<Escape>', lambda _: self.expr.set(''))
        self.calc_entry = entry
        self.calc_status = tk.StringVar(value='Enter 계산 · Esc 지우기')
        ttk.Label(b, textvariable=self.calc_status, wraplength=280).grid(row=2, column=0, sticky='w')
        keys = ttk.Frame(b)
        keys.grid(row=3, column=0, sticky='ew')
        for c in range(4): keys.columnconfigure(c, weight=1, uniform='keys')
        labels = ['C', '⌫', '(', ')', '7', '8', '9', '÷', '4', '5', '6', '×', '1', '2', '3', '−', '0', '.', '=', '+']
        for i, label in enumerate(labels):
            ttk.Button(keys, text=label, width=3, command=lambda x=label: self.calc_key(x)).grid(row=i//4, column=i%4, sticky='ew', padx=1, pady=1)
        self.calc.bind_wheels(self.calc.body)

    def build_memo(self):
        ttk.Label(self.memo, text='03  메모지', style='Title.TLabel').pack(anchor='w')
        self.memo_title = tk.StringVar()
        ttk.Label(self.memo, textvariable=self.memo_title).pack(anchor='w')
        holder = ttk.Frame(self.memo)
        holder.pack(fill='both', expand=True, pady=(4, 0))
        self.notes = tk.Text(holder, width=1, height=1, wrap='word', undo=True, font=('맑은 고딕', 11),
                             relief='solid', borderwidth=1, padx=6, pady=5)
        bar = ttk.Scrollbar(holder, orient='vertical', command=self.notes.yview)
        self.notes.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        self.notes.pack(fill='both', expand=True)
        self.notes.bind('<<Modified>>', self.note_changed)

    def collect(self):
        self.exam['title'] = self.title_var.get().strip()
        self.exam['round'] = self.round_var.get().strip()
        self.exam['answers'][self.current] = [v.get() for v in self.answer_vars]
        self.exam['notes'][self.current] = self.notes.get('1.0', 'end-1c')

    def changed(self):
        if self.job: self.after_cancel(self.job)
        self.job = self.after(450, self.persist)

    def persist(self):
        if self.job:
            self.after_cancel(self.job)
        self.job = None
        self.collect()
        try:
            atomic_json(self.draft_path, self.exam)
            self.status.set('자동 임시 저장 완료')
            return True
        except OSError as exc:
            self.status.set('임시 저장 실패 — 답안 저장을 이용하세요')
            return False

    def note_changed(self, _):
        if self.notes.edit_modified():
            self.notes.edit_modified(False)
            self.changed()

    def update_progress(self):
        row = self.exam['answers'][self.current]
        n = sum(bool(x) for x in row)
        total = sum(bool(x) for row in self.exam['answers'] for x in row)
        self.progress.set(f'응답 {n}/20 · 미응답 {20-n}  |  전체 {total}/100')

    def answer_changed(self):
        self.exam['answers'][self.current] = [v.get() for v in self.answer_vars]
        self.update_progress()
        self.changed()

    def clear_answer(self, row):
        self.answer_vars[row].set(0)
        self.answer_changed()

    def switch_subject(self, _=None):
        self.collect()
        self.current = SUBJECTS.index(self.subject_var.get())
        self.restore_subject()
        self.changed()

    def restore_subject(self):
        for var, value in zip(self.answer_vars, self.exam['answers'][self.current]): var.set(value)
        self.notes.delete('1.0', 'end')
        self.notes.insert('1.0', self.exam['notes'][self.current])
        self.notes.edit_reset()
        self.notes.edit_modified(False)
        self.memo_title.set(SUBJECTS[self.current] + ' · 과목별 자동 저장')
        self.update_progress()

    def calc_key(self, key):
        if key == 'C': self.expr.set('')
        elif key == '⌫':
            if self.calc_entry.selection_present():
                self.calc_entry.delete('sel.first', 'sel.last')
            else:
                pos = self.calc_entry.index('insert')
                if pos: self.calc_entry.delete(pos-1, pos)
        elif key == '=': self.evaluate()
        else:
            if self.calc_entry.selection_present(): self.calc_entry.delete('sel.first', 'sel.last')
            self.calc_entry.insert('insert', key)
        self.calc_entry.focus_set()

    def evaluate(self):
        try:
            result = calculate(self.expr.get())
            self.expr.set(result)
            self.calc_entry.icursor('end')
            self.calc_status.set('계산 완료')
        except ZeroDivisionError:
            self.calc_status.set('0으로 나눌 수 없습니다')
        except (ValueError, SyntaxError, OverflowError, RecursionError):
            self.calc_status.set('식을 확인하세요 · 사칙연산과 괄호 사용')

    def choose_folder(self):
        selected = filedialog.askdirectory(title='답안 저장 폴더 선택', initialdir=str(self.folder if self.folder.exists() else Path.home()))
        if not selected: return False
        old = self.folder
        self.folder = Path(selected)
        try:
            self.settings['folder'] = str(self.folder)
            atomic_json(self.settings_path, self.settings)
            self.status.set('저장 위치 변경 완료')
            return True
        except OSError as exc:
            self.folder = old
            messagebox.showerror('설정 저장 실패', str(exc))
            return False

    def save_txt(self):
        self.collect()
        if not self.exam['title']:
            messagebox.showwarning('시험 제목', '시험 제목을 입력한 뒤 저장하세요.')
            return False
        if 'folder' not in self.settings and not self.choose_folder(): return False
        try:
            matches = matching_exports(self.folder, self.exam)
            choice = False
            if matches:
                target = matches[0]
                extra = f'동일한 제목·회차 파일 {len(matches)}개 중 가장 최근 파일입니다.\n' if len(matches) > 1 else ''
                choice = messagebox.askyesnocancel(
                    '같은 시험의 답안이 있습니다',
                    f'시험: {self.exam["title"]} / {self.exam["round"] or "회차 미입력"}\n'
                    f'{extra}덮어쓸 파일: {target.name}\n\n'
                    '기존 답안과 메모, 직접 기입한 채점 내용도 교체됩니다.\n'
                    '예: 이 파일 덮어쓰기\n아니요: 기존 파일을 유지하고 별도 저장\n취소: 저장 중단',
                    parent=self, default=messagebox.CANCEL)
                if choice is None:
                    self.status.set('답안 TXT 저장 취소 · 입력 내용은 유지됩니다')
                    return False
            path = replace_export(matches[0], self.exam) if choice else export_exam(self.folder, self.exam)
            self.persist()
            self.status.set('답안 TXT 저장 완료')
            messagebox.showinfo('저장 완료', f'{path}\n\n답안지 폴더에서 파일을 채팅에 첨부하세요.')
            return True
        except OSError as exc:
            messagebox.showerror('답안 저장 실패', f'저장 위치나 여유 공간을 확인하세요.\n{exc}')
            return False

    def open_folder(self):
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            if sys.platform == 'win32': os.startfile(str(self.folder))
            else: subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(self.folder)])
        except OSError as exc:
            messagebox.showerror('폴더 열기 실패', str(exc))

    def copy_prompt(self):
        path = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent)) / 'grading_prompt.txt'
        try:
            prompt = path.read_text(encoding='utf-8')
            self.clipboard_clear()
            self.clipboard_append(prompt)
            self.update()
            self.status.set('채점 프롬프트 복사 완료 · 채팅에 붙여넣기')
        except OSError as exc:
            messagebox.showerror('프롬프트 읽기 실패', str(exc))

    def start_new(self):
        choice = messagebox.askyesnocancel('새 시험', '현재 시험을 TXT로 저장하고 새 시험을 시작할까요?\n예: 저장 후 시작 / 아니요: TXT 저장 없이 시작 / 취소: 돌아가기')
        if choice is None: return
        if choice and not self.save_txt(): return
        self.collect()
        try:
            atomic_json(self.data_dir / 'archives' / f'{self.exam["id"]}.json', self.exam)
        except OSError as exc:
            messagebox.showerror('기록 보관 실패', f'현재 시험을 유지합니다.\n{exc}')
            return
        self.exam = new_exam()
        self.current = 0
        self.title_var.set('')
        self.round_var.set('')
        self.subject_var.set(SUBJECTS[0])
        self.restore_subject()
        self.persist()

    def close(self):
        if self.job: self.after_cancel(self.job)
        if not self.persist():
            if not messagebox.askyesno('저장 실패', '임시 저장에 실패했습니다. 그래도 종료할까요?'): return
        self.destroy()


if __name__ == '__main__':
    App().mainloop()
