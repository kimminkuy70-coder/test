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
import time
import unicodedata
import uuid
import zipfile
from datetime import datetime
from xml.etree import ElementTree
from xml.sax.saxutils import escape
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

SUBJECTS = ("언어이해", "자료해석", "창의수리", "언어추리", "수열추리")
IS_MAC = sys.platform == "darwin"

FONT = "Apple SD Gothic Neo" if IS_MAC else "맑은 고딕"
FONT_SIZE = 13 if IS_MAC else 10
TIMER_SECONDS = 15 * 60


def expired_subjects(exam):
    """Subjects whose time ran out; older drafts have no such key."""
    expired = exam.get("expired")
    if not isinstance(expired, list):
        return []
    return sorted({i for i in expired if type(i) is int and 0 <= i < len(SUBJECTS)})


def default_data_dir(platform=sys.platform):
    if platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "AptitudeCompanion"
    return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AptitudeCompanion"


DATA_DIR = default_data_dir()


def new_exam():
    return {"id": str(uuid.uuid4()), "title": "", "round": "",
            "started": datetime.now().astimezone().isoformat(timespec="seconds"),
            "answers": [[0] * 20 for _ in SUBJECTS], "notes": [""] * 5}


def validate_exam(exam):
    if not isinstance(exam, dict):
        raise ValueError("시험 데이터 형식 오류")
    for key in ("id", "title", "round", "started"):
        if not isinstance(exam.get(key), str):
            raise ValueError("시험 정보 오류")
    answers = exam.get("answers")
    if not isinstance(answers, list) or len(answers) != 5:
        raise ValueError("과목 수 오류")
    if any(not isinstance(row, list) or len(row) != 20 or
           any(type(v) is not int or v not in range(6) for v in row) for row in answers):
        raise ValueError("답안 형식 오류")
    notes = exam.get("notes")
    if not isinstance(notes, list) or len(notes) != 5 or any(not isinstance(n, str) for n in notes):
        raise ValueError("메모 형식 오류")
    return exam


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix="draft-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


XLSX_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XLSX_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XLSX_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def xlsx_name(exam):
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", exam["title"]).strip(" .")[:65] or "시험"
    round_name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", exam["round"]).strip(" .")[:25] or "회차미입력"
    return f"{title}_{round_name}"


def read_cells(path):
    """Cell text per subject tab, for our own files and files re-saved by Excel (shared strings)."""
    cells = {}
    with zipfile.ZipFile(path) as z:
        names = set(z.namelist())
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ElementTree.fromstring(z.read("xl/sharedStrings.xml"))
            shared = ["".join(t.text or "" for t in si.iter(f"{{{XLSX_MAIN}}}t")) for si in root.iter(f"{{{XLSX_MAIN}}}si")]
        rels = ElementTree.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        targets = {r.get("Id"): r.get("Target") for r in rels.iter(f"{{{XLSX_PKG}}}Relationship")}
        book = ElementTree.fromstring(z.read("xl/workbook.xml"))
        for sheet in book.iter(f"{{{XLSX_MAIN}}}sheet"):
            name, target = sheet.get("name"), targets.get(sheet.get(f"{{{XLSX_REL}}}id"), "")
            if name not in SUBJECTS or not target:
                continue
            target = target.lstrip("/") if target.startswith("/") else "xl/" + target
            if target not in names:
                continue
            values = {}
            for cell in ElementTree.fromstring(z.read(target)).iter(f"{{{XLSX_MAIN}}}c"):
                kind, v = cell.get("t"), cell.find(f"{{{XLSX_MAIN}}}v")
                if kind == "inlineStr":
                    value = "".join(t.text or "" for t in cell.iter(f"{{{XLSX_MAIN}}}t"))
                elif v is None or v.text is None:
                    continue
                elif kind == "s":
                    value = shared[int(v.text)] if int(v.text) < len(shared) else ""
                else:
                    value = v.text
                if value.strip():
                    values[cell.get("r", "")] = value.strip()
            cells[name] = values
    return cells


def read_answer_keys(cells):
    """Correct answers typed into column C, so an update never wipes them."""
    return {name: {int(ref[1:]): value for ref, value in values.items()
                   if re.fullmatch(r"C\d+", ref) and 2 <= int(ref[1:]) <= 21}
            for name, values in cells.items()}


def read_exam_id(cells):
    """The 시험 식별번호 recorded in the file, or "" for files written before it was added."""
    for values in cells.values():
        for ref, value in values.items():
            if value == "시험 식별번호" and ref.startswith("A"):
                return values.get("B" + ref[1:], "")
    return ""


def xlsx_text(value):
    """Drop characters XML 1.0 forbids (pasted control codes, lone surrogates); Excel rejects the file otherwise."""
    return escape(re.sub("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", "", str(value)))


def xlsx_cell(ref, value, style=0):
    s = f' s="{style}"' if style else ""
    if value is None or value == "":
        return f'<c r="{ref}"{s}/>'
    # Only real numbers become numbers; a title or round like "01" stays text.
    if isinstance(value, (int, float)):
        return f'<c r="{ref}"{s}><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{s}><is><t xml:space="preserve">{xlsx_text(value)}</t></is></c>'


def xlsx_sheet(exam, index, keys):
    rows = [[xlsx_cell(f"{c}1", h, 1) for c, h in zip("ABCD", ("문항", "내 답", "정답", "결과"))]]
    for i, answer in enumerate(exam["answers"][index], 2):
        result = f'<c r="D{i}" t="str"><f>IF(C{i}="","",IF(B{i}="","미응답",IF(B{i}=C{i},"O","X")))</f></c>'
        key = keys.get(i, "")
        if re.fullmatch(r"-?\d+(\.\d+)?", key):
            key = float(key) if "." in key else int(key)  # B=C compares numbers, not text
        rows.append([xlsx_cell(f"A{i}", i - 1), xlsx_cell(f"B{i}", answer or ""), xlsx_cell(f"C{i}", key), result])
    expired = index in expired_subjects(exam) or index in expired_subjects({"expired": exam.get("timed_out")})
    formulas = (("정답 수", 'COUNTIF(D2:D21,"O")'), ("오답 수", 'COUNTIF(D2:D21,"X")'), ("미응답", "COUNTBLANK(B2:B21)"))
    values = (("시간 종료", "예" if expired else "아니요"), ("메모", exam["notes"][index]),
              ("저장 일시", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
              # Exam identity for grading (the file replaces the old TXT export).
              ("시험 제목", exam["title"]), ("회차", exam["round"] or "미입력"),
              ("응시 일시", exam["started"]), ("시험 식별번호", exam["id"]))
    rows.append([])
    for r, (label, formula) in enumerate(formulas, 23):
        rows.append([xlsx_cell(f"A{r}", label, 1), f'<c r="B{r}"><f>{escape(formula)}</f></c>'])
    for r, (label, value) in enumerate(values, 23 + len(formulas)):
        rows.append([xlsx_cell(f"A{r}", label, 1), xlsx_cell(f"B{r}", value)])
    data = "".join(f'<row r="{r}">{"".join(cells)}</row>' for r, cells in enumerate(rows, 1) if cells)
    return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<worksheet xmlns="{XLSX_MAIN}"><sheetViews><sheetView workbookViewId="0">'
            '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
            '<cols><col min="1" max="1" width="10" customWidth="1"/><col min="2" max="4" width="12" customWidth="1"/></cols>'
            f"<sheetData>{data}</sheetData></worksheet>")


def xlsx_path(folder, exam):
    """[제목_회차].xlsx in the answer folder. The same exam always rewrites that file;
    a different exam (another 시험 식별번호) with the same title and round gets _2, _3...
    A file that cannot be read as an answer workbook is never overwritten."""
    base = unicodedata.normalize("NFC", xlsx_name(exam))
    n = 1
    while True:
        path = folder / (f"{base}.xlsx" if n == 1 else f"{base}_{n}.xlsx")
        if not path.exists():
            return path
        try:
            cells = read_cells(path)
            # "" only for our own workbooks written before the id was added.
            owner = read_exam_id(cells) if cells else None
        except (zipfile.BadZipFile, ElementTree.ParseError, KeyError, ValueError, OSError):
            owner = None
        if owner in ("", exam["id"]):
            return path
        n += 1


def write_xlsx(path, exam):
    """One tab per subject; correct answers already typed into the file are kept."""
    try:
        keys = read_answer_keys(read_cells(path)) if path.exists() else {}
    except (zipfile.BadZipFile, ElementTree.ParseError, KeyError, ValueError):
        keys = {}
    n = len(SUBJECTS)
    files = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            + "".join(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' for i in range(1, n + 1))
            + "</Types>",
        "_rels/.rels": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{XLSX_PKG}">'
            f'<Relationship Id="rId1" Type="{XLSX_REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="{XLSX_MAIN}" xmlns:r="{XLSX_REL}"><sheets>'
            + "".join(f'<sheet name="{s}" sheetId="{i}" r:id="rId{i}"/>' for i, s in enumerate(SUBJECTS, 1))
            + '</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>',
        "xl/_rels/workbook.xml.rels": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="{XLSX_PKG}">'
            + "".join(f'<Relationship Id="rId{i}" Type="{XLSX_REL}/worksheet" Target="worksheets/sheet{i}.xml"/>' for i in range(1, n + 1))
            + f'<Relationship Id="rId{n + 1}" Type="{XLSX_REL}/styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml": f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="{XLSX_MAIN}">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>',
    }
    for i, subject in enumerate(SUBJECTS):
        files[f"xl/worksheets/sheet{i + 1}.xml"] = xlsx_sheet(exam, i, keys.get(subject, {}))
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix="answer-", suffix=".tmp")
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as z:
            for name, text in files.items():
                z.writestr(name, text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return path


def calculate(expression):
    """Evaluate only finite arithmetic, never arbitrary Python."""
    expression = expression.replace("×", "*").replace("÷", "/").replace("−", "-")
    if not expression.strip() or len(expression) > 150:
        raise ValueError("식을 입력하세요 (최대 150자)")
    tree = ast.parse(expression, mode="eval")
    if len(list(ast.walk(tree))) > 100:
        raise ValueError("식이 너무 깁니다")

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
            raise ValueError("사칙연산과 괄호만 사용할 수 있습니다")
        if abs(value) > 1e100 or not math.isfinite(value):
            raise ValueError("계산 범위를 초과했습니다")
        return value

    return format(visit(tree.body), ".12g")


class ScrollPanel(ttk.Frame):
    """Each pane owns its scroll area; shrinking cannot overlap adjacent panes."""
    def __init__(self, parent):
        super().__init__(parent)
        self.canvas = tk.Canvas(self, highlightthickness=0, bg="#f5f7fb", width=1, height=1)
        bar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=bar.set)
        if IS_MAC:
            self.canvas.configure(yscrollincrement=10)
        self.canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self.body = ttk.Frame(self.canvas, padding=8)
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self.window, width=e.width))
        self.touch_pixels = 0.0
        # Wheel over any child scrolls only this pane.
        self.bind_wheels(self)

    def bind_wheels(self, widget):
        widget.bind("<MouseWheel>", self.wheel, add="+")
        widget.bind("<Button-4>", lambda _: self.canvas.yview_scroll(-3, "units"), add="+")
        widget.bind("<Button-5>", lambda _: self.canvas.yview_scroll(3, "units"), add="+")
        try:
            # Tk 9 reports trackpad scrolling as its own event instead of <MouseWheel>.
            widget.bind("<TouchpadScroll>", self.touchpad, add="+")
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self.bind_wheels(child)

    def touchpad(self, event):
        try:
            _, dy = (int(v) for v in self.tk.splitlist(self.tk.call("tk::PreciseScrollDeltas", event.delta)))
        except (tk.TclError, ValueError):
            return "break"
        # Deltas are pixels; carry the remainder so slow swipes still move.
        step = int(self.canvas.cget("yscrollincrement") or 0) or 10
        self.touch_pixels -= dy
        units = int(self.touch_pixels / step)
        if units:
            self.touch_pixels -= units * step
            self.canvas.yview_scroll(units, "units")
        return "break"

    def wheel(self, event):
        if IS_MAC:
            # Trackpads send small deltas; mice send multiples of 120.
            steps = -event.delta if abs(event.delta) < 120 else -3 * int(event.delta / 120)
        else:
            steps = -int(event.delta / 120) if abs(event.delta) >= 120 else (-1 if event.delta > 0 else 1)
        self.canvas.yview_scroll(steps, "units")
        return "break"


class App(tk.Tk):
    def __init__(self, data_dir=DATA_DIR):
        super().__init__()
        self.title("인적성 시험 도우미")
        self.data_dir = Path(data_dir)
        self.draft_path = self.data_dir / "draft.json"
        self.settings_path = self.data_dir / "settings.json"
        self.exam = new_exam()
        self.settings = {}
        self.load_warning = ""
        self.job = None
        self.current = 0
        self.timer_job = None
        self.deadline = None
        try:
            if self.settings_path.exists():
                self.settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
                if not isinstance(self.settings, dict): self.settings = {}
            if self.draft_path.exists():
                self.exam = validate_exam(json.loads(self.draft_path.read_text(encoding="utf-8")))
        except (ValueError, OSError) as exc:
            self.load_warning = f"이전 기록을 복원하지 못했습니다: {exc}"
            if self.draft_path.exists():
                try:
                    self.draft_path.rename(self.draft_path.with_name(f"draft-damaged-{uuid.uuid4().hex[:8]}.json"))
                except OSError:
                    pass
        self.exam["expired"] = expired_subjects(self.exam)
        self.exam.pop("auto_export", None)  # left by builds that also wrote TXT files
        self.folder = Path(self.settings.get("folder", str(Path.home() / "Documents" / "인적성답안")))
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=(FONT, FONT_SIZE), background="#f5f7fb")
        style.configure("TButton", padding=(5, 5))
        style.configure("Title.TLabel", font=(FONT, FONT_SIZE + 1, "bold"), foreground="#17365d")
        style.configure("TRadiobutton", padding=(2, 5))
        style.configure("Small.TButton", padding=(3, 1))
        style.configure("Timer.TFrame", background="#17365d")
        style.configure("Timer.TLabel", background="#17365d", foreground="#ffffff")
        style.configure("Clock.TLabel", background="#17365d", foreground="#ffffff",
                        font=(FONT, FONT_SIZE + 8, "bold"))
        style.configure("Warn.Clock.TLabel", foreground="#ff8a80")
        self.minsize(360, 540)
        # Fit the screen: tall narrow window on the right edge.
        height = min(900, max(540, self.winfo_screenheight() - (150 if IS_MAC else 100)))
        self.geometry(f"410x{height}+{max(0, self.winfo_screenwidth() - 430)}+30")

        self.build_timer()
        self.panes = tk.PanedWindow(self, orient="vertical", sashwidth=9, sashrelief="raised",
                                    bg="#cad5e5", borderwidth=0, opaqueresize=True)
        self.panes.pack(fill="both", expand=True)
        # The answer-sheet header stays fixed; only the subject and answer rows scroll.
        self.omr_pane = ttk.Frame(self.panes)
        self.omr_head = ttk.Frame(self.omr_pane, padding=(8, 5, 8, 4))
        self.omr_head.pack(side="top", fill="x")
        ttk.Separator(self.omr_pane).pack(side="top", fill="x")
        self.omr = ScrollPanel(self.omr_pane)
        self.omr.pack(fill="both", expand=True)
        self.calc = ScrollPanel(self.panes)
        self.memo = ttk.Frame(self.panes, padding=8)
        self.panes.add(self.omr_pane, minsize=150, stretch="always", height=int(height * 0.53))
        self.panes.add(self.calc, minsize=105, stretch="always", height=int(height * 0.29))
        self.panes.add(self.memo, minsize=95, stretch="always")
        self.build_omr()
        self.build_calculator()
        self.build_memo()
        self.status = tk.StringVar(value="이전 응시 기록 복원 완료" if self.draft_path.exists() else "새 시험을 시작하세요")
        ttk.Label(self, textvariable=self.status, anchor="w", padding=(7, 4), wraplength=330).pack(fill="x")
        self.update_idletasks()

        width_min = max(360, self.omr.body.winfo_reqwidth() + 26, self.omr_head.winfo_reqwidth(),
                        self.calc.body.winfo_reqwidth() + 26)
        scale = max(1.0, float(self.tk.call("tk", "scaling")) / (96 / 72))
        self.pane_minimums = (self.omr_head.winfo_reqheight() + round(90 * scale),
                              round(105 * scale), round(95 * scale))
        for pane, minimum in zip((self.omr_pane, self.calc, self.memo), self.pane_minimums):
            self.panes.paneconfigure(pane, minsize=minimum)
        height_min = max(540, sum(self.pane_minimums) + 90 + self.timer_bar.winfo_reqheight())
        self.minsize(width_min, height_min)
        width = max(410, width_min)
        height = max(height, height_min)
        self.geometry(f"{width}x{height}+{max(0, self.winfo_screenwidth() - width - 20)}+30")
        self.protocol("WM_DELETE_WINDOW", self.close)
        if IS_MAC:
            # Cmd+Q goes through the same save path as the close button.
            self.createcommand("tk::mac::Quit", self.close)
        self.restore_subject()
        self.title_var.trace_add("write", lambda *_: self.changed())
        self.round_var.trace_add("write", lambda *_: self.changed())
        if self.load_warning:
            self.after(100, lambda: messagebox.showwarning("복원 확인", self.load_warning))

    def build_timer(self):
        bar = ttk.Frame(self, padding=(10, 6), style="Timer.TFrame")
        bar.pack(side="top", fill="x")
        bar.columnconfigure(1, weight=1)
        self.timer_title = tk.StringVar()
        ttk.Label(bar, textvariable=self.timer_title, style="Timer.TLabel").grid(row=0, column=0, sticky="w")
        self.timer_text = tk.StringVar()
        self.timer_label = ttk.Label(bar, textvariable=self.timer_text, style="Clock.TLabel")
        self.timer_label.grid(row=0, column=1)
        self.timer_button = ttk.Button(bar, text="시작", width=6, command=self.start_timer)
        self.timer_button.grid(row=0, column=2, sticky="e")
        self.timer_bar = bar

    def build_omr(self):
        head = self.omr_head
        head.columnconfigure(0, weight=1)
        ttk.Label(head, text="01  답안지", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.top = tk.BooleanVar(value=False)
        ttk.Checkbutton(head, text="항상 위", variable=self.top,
                        command=lambda: self.attributes("-topmost", self.top.get())).grid(row=0, column=1, sticky="e")
        self.title_var = tk.StringVar(value=self.exam["title"])
        self.round_var = tk.StringVar(value=self.exam["round"])
        info = ttk.Frame(head)
        info.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(3, 3))
        info.columnconfigure(1, weight=1)
        ttk.Label(info, text="제목 ").grid(row=0, column=0)
        ttk.Entry(info, textvariable=self.title_var, width=8).grid(row=0, column=1, sticky="ew")
        ttk.Label(info, text="  회차 ").grid(row=0, column=2)
        ttk.Entry(info, textvariable=self.round_var, width=5).grid(row=0, column=3)
        ttk.Button(info, text="새 시험", style="Small.TButton", width=0, command=self.start_new).grid(row=0, column=4, padx=(6, 0))
        buttons = ttk.Frame(head)
        buttons.grid(row=2, column=0, columnspan=2, sticky="ew")
        for c in range(4): buttons.columnconfigure(c, weight=1)
        for i, (label, fn) in enumerate((("답안 저장", self.save_answers), ("폴더 열기", self.open_folder),
                                         ("위치 변경", self.choose_folder), ("프롬프트 복사", self.copy_prompt))):
            ttk.Button(buttons, text=label, style="Small.TButton", width=0, command=fn).grid(row=0, column=i, sticky="ew", padx=1)
        body = self.omr.body
        body.columnconfigure(0, weight=1)
        self.subject_var = tk.StringVar(value=SUBJECTS[0])
        selector = ttk.Combobox(body, textvariable=self.subject_var, values=SUBJECTS, state="readonly", width=15)
        selector.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        selector.bind("<<ComboboxSelected>>", self.switch_subject)
        self.progress = tk.StringVar()
        ttk.Label(body, textvariable=self.progress).grid(row=1, column=0, columnspan=2, sticky="w")
        grid = ttk.Frame(body)
        grid.grid(row=2, column=0, columnspan=2, sticky="ew", pady=5)
        for c in range(1, 6): grid.columnconfigure(c, weight=1, uniform="choices")
        self.answer_vars = []
        self.answer_widgets = []
        for row in range(20):
            var = tk.IntVar()
            self.answer_vars.append(var)
            ttk.Label(grid, text=f"{row + 1:02d}", width=3).grid(row=row, column=0, sticky="w")
            for choice in range(1, 6):
                radio = ttk.Radiobutton(grid, text=str(choice), variable=var, value=choice,
                                        command=self.answer_changed)
                radio.grid(row=row, column=choice, sticky="ew")
                self.answer_widgets.append(radio)
            clear = ttk.Button(grid, text="해제", width=4, command=lambda r=row: self.clear_answer(r))
            clear.grid(row=row, column=6, pady=1)
            self.answer_widgets.append(clear)
        self.omr.bind_wheels(self.omr.body)

    def build_calculator(self):
        b = self.calc.body
        b.columnconfigure(0, weight=1)
        ttk.Label(b, text="02  계산기", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.expr = tk.StringVar()
        entry = ttk.Entry(b, textvariable=self.expr, justify="right", width=12, font=(FONT, FONT_SIZE + 4))
        entry.grid(row=1, column=0, sticky="ew", pady=5)
        entry.bind("<Return>", lambda _: self.evaluate())
        entry.bind("<KP_Enter>", lambda _: self.evaluate())
        entry.bind("<Escape>", lambda _: self.expr.set(""))
        self.calc_entry = entry
        self.calc_status = tk.StringVar(value="Enter 계산 · Esc 지우기")
        ttk.Label(b, textvariable=self.calc_status, wraplength=280).grid(row=2, column=0, sticky="w")
        keys = ttk.Frame(b)
        keys.grid(row=3, column=0, sticky="ew")
        for c in range(4): keys.columnconfigure(c, weight=1, uniform="keys")
        labels = ["C", "⌫", "(", ")", "7", "8", "9", "÷", "4", "5", "6", "×", "1", "2", "3", "−", "0", ".", "=", "+"]
        for i, label in enumerate(labels):
            ttk.Button(keys, text=label, width=3, command=lambda x=label: self.calc_key(x)).grid(row=i // 4, column=i % 4, sticky="ew", padx=1, pady=1)
        self.calc.bind_wheels(self.calc.body)

    def build_memo(self):
        ttk.Label(self.memo, text="03  메모지", style="Title.TLabel").pack(anchor="w")
        self.memo_title = tk.StringVar()
        ttk.Label(self.memo, textvariable=self.memo_title).pack(anchor="w")
        holder = ttk.Frame(self.memo)
        holder.pack(fill="both", expand=True, pady=(4, 0))
        self.notes = tk.Text(holder, width=1, height=1, wrap="word", undo=True, font=(FONT, FONT_SIZE + 1),
                             relief="solid", borderwidth=1, padx=6, pady=5)
        bar = ttk.Scrollbar(holder, orient="vertical", command=self.notes.yview)
        self.notes.configure(yscrollcommand=bar.set)
        bar.pack(side="right", fill="y")
        self.notes.pack(fill="both", expand=True)
        self.notes.bind("<<Modified>>", self.note_changed)

    def collect(self):
        self.exam["title"] = self.title_var.get().strip()
        self.exam["round"] = self.round_var.get().strip()
        self.exam["answers"][self.current] = [v.get() for v in self.answer_vars]
        self.exam["notes"][self.current] = self.notes.get("1.0", "end-1c")

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
            self.status.set("자동 임시 저장 완료")
            return True
        except OSError as exc:
            self.status.set("임시 저장 실패 — 답안 저장을 이용하세요")
            return False

    def note_changed(self, _):
        if self.notes.edit_modified():
            self.notes.edit_modified(False)
            self.changed()

    def update_progress(self):
        row = self.exam["answers"][self.current]
        n = sum(bool(x) for x in row)
        total = sum(bool(x) for row in self.exam["answers"] for x in row)
        self.progress.set(f"응답 {n}/20 · 미응답 {20 - n}  |  전체 {total}/100")

    def answer_changed(self):
        self.exam["answers"][self.current] = [v.get() for v in self.answer_vars]
        self.update_progress()
        self.changed()

    def clear_answer(self, row):
        self.answer_vars[row].set(0)
        self.answer_changed()

    def switch_subject(self, _=None):
        index = SUBJECTS.index(self.subject_var.get())
        if index == self.current: return  # re-selecting the same subject must not reset its timer
        self.collect()
        self.current = index
        self.restore_subject()
        self.changed()

    def restore_subject(self):
        for var, value in zip(self.answer_vars, self.exam["answers"][self.current]): var.set(value)
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", self.exam["notes"][self.current])
        self.notes.edit_reset()
        self.notes.edit_modified(False)
        self.memo_title.set(SUBJECTS[self.current] + " · 과목별 자동 저장")
        self.update_progress()
        self.reset_timer()

    def reset_timer(self):
        """Every subject change starts from a fresh 15:00; expired subjects stay locked."""
        if self.timer_job: self.after_cancel(self.timer_job)
        self.timer_job = None
        self.deadline = None
        expired = self.current in expired_subjects(self.exam)
        self.timer_title.set(f"{SUBJECTS[self.current]} 타이머" + (" · 종료" if expired else ""))
        self.show_time(0 if expired else TIMER_SECONDS)
        self.timer_button.state(["disabled"] if expired else ["!disabled"])
        for widget in self.answer_widgets:
            widget.state(["disabled"] if expired else ["!disabled"])

    def show_time(self, seconds):
        self.timer_text.set(f"{seconds // 60:02d}:{seconds % 60:02d}")
        self.timer_label.configure(style="Warn.Clock.TLabel" if seconds <= 60 else "Clock.TLabel")

    def start_timer(self):
        if self.deadline is not None or self.current in expired_subjects(self.exam): return
        self.deadline = time.monotonic() + TIMER_SECONDS
        self.timer_button.state(["disabled"])
        self.status.set(f"{SUBJECTS[self.current]} 타이머 시작 · 15분")
        self.tick()

    def tick(self):
        # Measure against a monotonic deadline so a busy event loop cannot slow the clock.
        remaining = max(0, math.ceil(self.deadline - time.monotonic()))
        self.show_time(remaining)
        if remaining:
            self.timer_job = self.after(200, self.tick)
        else:
            self.time_up()

    def time_up(self):
        self.timer_job = None
        self.deadline = None
        self.collect()
        self.exam["expired"] = sorted(set(expired_subjects(self.exam)) | {self.current})
        # Lock state is cleared on a manual save; this record of which subjects ran out is not.
        self.exam["timed_out"] = sorted(set(expired_subjects({"expired": self.exam.get("timed_out")})) | {self.current})
        self.reset_timer()
        self.status.set(self.auto_save())
        messagebox.showwarning("시간 종료", "시간이 종료되었습니다", parent=self)

    def auto_save(self):
        """Save without dialogs when time runs out: the draft, then this exam's Excel file."""
        if not self.persist():
            return "시간 종료 · 임시 저장 실패 — 답안 저장을 이용하세요"
        if not self.exam["title"]:
            return "시간 종료 · 임시 저장 완료 (시험 제목이 없어 엑셀 저장은 건너뜀)"
        try:
            path = self.save_xlsx()
            self.persist()
            return f"시간 종료 · 엑셀 자동 저장 완료 ({path.name})"
        except OSError as exc:
            return f"시간 종료 · 임시 저장 완료, 엑셀 저장 실패 (파일이 열려 있으면 닫고 답안 저장): {exc}"

    def save_xlsx(self):
        path = xlsx_path(self.folder, self.exam)
        write_xlsx(path, self.exam)
        self.exam["xlsx"] = str(path)
        return path

    def calc_key(self, key):
        if key == "C": self.expr.set("")
        elif key == "⌫":
            if self.calc_entry.selection_present():
                self.calc_entry.delete("sel.first", "sel.last")
            else:
                pos = self.calc_entry.index("insert")
                if pos: self.calc_entry.delete(pos - 1, pos)
        elif key == "=": self.evaluate()
        else:
            if self.calc_entry.selection_present(): self.calc_entry.delete("sel.first", "sel.last")
            self.calc_entry.insert("insert", key)
        self.calc_entry.focus_set()

    def evaluate(self):
        try:
            result = calculate(self.expr.get())
            self.expr.set(result)
            self.calc_entry.icursor("end")
            self.calc_status.set("계산 완료")
        except ZeroDivisionError:
            self.calc_status.set("0으로 나눌 수 없습니다")
        except (ValueError, SyntaxError, OverflowError, RecursionError):
            self.calc_status.set("식을 확인하세요 · 사칙연산과 괄호 사용")

    def choose_folder(self):
        selected = filedialog.askdirectory(title="답안 저장 폴더 선택", initialdir=str(self.folder if self.folder.exists() else Path.home()))
        if not selected: return False
        old = self.folder
        self.folder = Path(selected)
        try:
            self.settings["folder"] = str(self.folder)
            atomic_json(self.settings_path, self.settings)
            self.status.set("저장 위치 변경 완료")
            return True
        except OSError as exc:
            self.folder = old
            messagebox.showerror("설정 저장 실패", str(exc))
            return False

    def save_answers(self):
        self.collect()
        if not self.exam["title"]:
            messagebox.showwarning("시험 제목", "시험 제목을 입력한 뒤 저장하세요.")
            return False
        if "folder" not in self.settings and not self.choose_folder(): return False
        try:
            path = self.save_xlsx()
        except OSError as exc:
            messagebox.showerror("답안 저장 실패", "엑셀에서 이 파일이 열려 있으면 닫은 뒤 다시 저장하세요.\n"
                                 f"저장 위치나 여유 공간도 확인하세요.\n{exc}")
            return False
        # A manual save closes the exam: the file keeps the time-up record, the sheet unlocks again.
        self.exam["expired"] = []
        if self.deadline is None: self.reset_timer()  # never restart a clock that is still running
        self.persist()
        self.status.set("엑셀 저장 완료 · 타이머·답안지 잠금 해제")
        messagebox.showinfo("저장 완료", f"{path}\n\n답안지 폴더에서 파일을 채팅에 첨부하세요.")
        return True

    def open_folder(self):
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            if sys.platform == "win32": os.startfile(str(self.folder))
            else: subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(self.folder)])
        except OSError as exc:
            messagebox.showerror("폴더 열기 실패", str(exc))

    def copy_prompt(self):
        path = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "grading_prompt.txt"
        try:
            prompt = path.read_text(encoding="utf-8")
            self.clipboard_clear()
            self.clipboard_append(prompt)
            self.update()
            self.status.set("채점 프롬프트 복사 완료 · 채팅에 붙여넣기")
        except OSError as exc:
            messagebox.showerror("프롬프트 읽기 실패", str(exc))

    def start_new(self):
        choice = messagebox.askyesnocancel("새 시험", "현재 시험을 엑셀로 저장하고 새 시험을 시작할까요?\n예: 저장 후 시작 / 아니요: 저장 없이 시작 / 취소: 돌아가기")
        if choice is None: return
        if choice and not self.save_answers(): return
        self.collect()
        try:
            atomic_json(self.data_dir / "archives" / f"{self.exam['id']}.json", self.exam)
        except OSError as exc:
            messagebox.showerror("기록 보관 실패", f"현재 시험을 유지합니다.\n{exc}")
            return
        self.exam = new_exam()
        self.current = 0
        self.title_var.set("")
        self.round_var.set("")
        self.subject_var.set(SUBJECTS[0])
        self.restore_subject()
        self.persist()

    def close(self):
        if self.job: self.after_cancel(self.job)
        if self.timer_job: self.after_cancel(self.timer_job)
        if not self.persist():
            if not messagebox.askyesno("저장 실패", "임시 저장에 실패했습니다. 그래도 종료할까요?"): return
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
