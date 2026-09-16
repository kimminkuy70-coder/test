"""Run on a desktop/Windows runner to exercise actual Tk geometry."""
import tempfile
from pathlib import Path
from app import App

with tempfile.TemporaryDirectory() as folder:
    app = App(Path(folder))
    app.update()
    for width, height in ((360, 540), (410, 900), (700, 600), (360, 700)):
        app.geometry(f'{width}x{height}')
        app.update()
        for positions in ((155, 270), (200, height-160), (height//2, height-110)):
            app.panes.sash_place(0, 0, positions[0])
            app.panes.sash_place(1, 0, positions[1])
            app.update()
            panes = [app.omr, app.calc, app.memo]
            for i, pane in enumerate(panes):
                assert pane.winfo_width() > 0 and pane.winfo_height() >= (150, 105, 95)[i]
                if i:
                    assert panes[i-1].winfo_y() + panes[i-1].winfo_height() <= pane.winfo_y()
            for panel in (app.omr, app.calc):
                assert panel.body.winfo_width() <= panel.canvas.winfo_width()
                for child in panel.body.winfo_children():
                    assert child.winfo_x() + child.winfo_width() <= panel.body.winfo_width(), str(child)
    app.title_var.set('화면 검증')
    app.answer_vars[0].set(3)
    app.answer_changed()
    app.notes.insert('1.0', '언어이해 메모')
    app.subject_var.set('자료해석')
    app.switch_subject()
    app.answer_vars[0].set(5)
    app.answer_changed()
    app.subject_var.set('언어이해')
    app.switch_subject()
    assert app.answer_vars[0].get() == 3
    assert app.notes.get('1.0', 'end-1c') == '언어이해 메모'
    assert app.persist()
    app.destroy()
    app = App(Path(folder))
    app.update()
    assert app.answer_vars[0].get() == 3
    assert app.exam['answers'][1][0] == 5
    assert app.notes.get('1.0', 'end-1c') == '언어이해 메모'
    app.destroy()
print('UI geometry, pane boundaries, subject switching and restart checks passed.')
