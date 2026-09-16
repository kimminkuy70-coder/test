"""Windows Tk layout tests using simulated screen metrics and font DPI.
These do not change the runner's physical monitor resolution or Windows DPI.
"""
import json
import tempfile
from pathlib import Path
from tkinter import ttk
from app import App

REPORT = []

class ProfileApp(App):
    resolution = (1920, 1080)
    percent = 100

    def winfo_screenheight(self):
        self.tk.call('tk', 'scaling', (96 / 72) * self.percent / 100)
        return self.resolution[1]

    def winfo_screenwidth(self):
        return self.resolution[0]


def inspect(app):
    panes = [app.omr, app.calc, app.memo]
    for i, pane in enumerate(panes):
        assert pane.winfo_height() >= (150, 105, 95)[i], ('pane height', i, pane.winfo_height())
        if i:
            assert panes[i-1].winfo_y() + panes[i-1].winfo_height() <= pane.winfo_y(), 'pane overlap'
    def check_children(parent):
        for child in parent.winfo_children():
            assert child.winfo_x() >= 0, ('left clipping', str(child))
            assert child.winfo_x() + child.winfo_width() <= parent.winfo_width(), ('right clipping', str(child), child.winfo_x(), child.winfo_width(), parent.winfo_width())
            if isinstance(child, (ttk.Button, ttk.Radiobutton, ttk.Checkbutton, ttk.Label)):
                assert child.winfo_width() >= child.winfo_reqwidth(), ('text clipping', str(child), child.winfo_width(), child.winfo_reqwidth())
            if isinstance(child, ttk.Frame):
                check_children(child)
    for panel in (app.omr, app.calc):
        check_children(panel.body)
        panel.canvas.yview_moveto(1)
        app.update()
        assert abs(panel.canvas.yview()[1] - 1) < .01, 'cannot reach end'
        panel.canvas.yview_moveto(0)
    assert app.notes.winfo_height() > 0


def run_profile(resolution, percent):
    ProfileApp.resolution, ProfileApp.percent = resolution, percent
    with tempfile.TemporaryDirectory() as folder:
        app = ProfileApp(Path(folder))
        app.maxsize(*resolution)
        app.update()
        app.geometry('+0+0')
        cases = [(360,540), (410,900), (resolution[0]//3,resolution[1]-100), (resolution[0]//2,resolution[1]-100)]
        completed = 0
        for width, height in cases:
            app.geometry(f'{width}x{height}+0+0')
            app.update()
            height = app.winfo_height()
            for positions in ((155,270), (200,height-160), (height//2,height-110)):
                app.panes.sash_place(0,0,positions[0])
                app.panes.sash_place(1,0,positions[1])
                app.update()
                inspect(app)
                completed += 1
        app.title_var.set('Display test')
        app.answer_vars[0].set(3)
        app.answer_changed()
        app.notes.insert('1.0','메모 검증\n' * 100)
        app.subject_var.set('자료해석'); app.switch_subject()
        app.answer_vars[0].set(5); app.answer_changed()
        app.subject_var.set('언어이해'); app.switch_subject()
        assert app.answer_vars[0].get() == 3
        assert app.notes.get('1.0','end-1c') == '메모 검증\n' * 100
        assert app.persist()
        app.destroy()
        app = ProfileApp(Path(folder)); app.update()
        assert app.answer_vars[0].get() == 3 and app.exam['answers'][1][0] == 5
        assert app.notes.get('1.0','end-1c') == '메모 검증\n' * 100
        minimum = app.minsize()
        app.destroy()
        return {'resolution':resolution, 'scale_percent':percent, 'layouts':completed, 'minimum_window':minimum, 'status':'passed'}

if __name__ == '__main__':
    for resolution in ((1920,1080),(2880,1800)):
        for percent in (100,125,150,200):
            try:
                result = run_profile(resolution,percent)
            except Exception as exc:
                result = {'resolution':resolution,'scale_percent':percent,'status':'failed','error':str(exc)}
                REPORT.append(result)
                print(json.dumps(result),flush=True)
                Path('display-test-results.json').write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
                raise
            REPORT.append(result)
            print(json.dumps(result),flush=True)
    Path('display-test-results.json').write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
