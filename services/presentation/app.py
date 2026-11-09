"""KctApp: a clickable app inside Jupyter (no web server, no open port).

    from services.app import boot
    from services.presentation.app import KctApp
    KctApp(boot())            # last line of a cell: shows the app

One case at a time (chosen at the top), one tab per step of the work. Tabs and buttons of
later releases are shown greyed out, marked "soon":

    1 Case         upload the control details and the test plan (PDF) -> a new case
    2 Test steps   run the interpretation, browse the steps and their criteria

After each step a "Next" button leads to the next tab.
Every button calls a plain method (create_case, interpret, ...), so the same work can be done
from code and is tested without a screen. All work is done by the app's services, exactly as
through the API or the other notebooks. Needs ipywidgets (it comes with most Jupyter installations).
"""
from __future__ import annotations

import traceback
from contextlib import contextmanager
from typing import List, Optional

from services.presentation import notebook as show

# Flowbite/Tailwind-like look, written as plain CSS (no Tailwind build, no CDN: works offline).
# Scoped to .kct-app; covers JupyterLab 4 / ipywidgets 8 (lm-*) and older (p-*) class names.
ORANGE, ORANGE_DARK, NAVY = "#FF6200", "#E55800", "#000066"
STYLE = """
<style>
.kct-app { font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif; color: #111827; gap: 10px; }
.kct-app .widget-label { color: #4B5563 !important; font-weight: 500; }
/* tabs: pills on a grey bar */
.kct-app .kct-tabs > .lm-TabBar, .kct-app .kct-tabs > .p-TabBar, .kct-app .kct-tabs .widget-tab-bar {
  background: #F3F4F6 !important; border-radius: 12px; padding: 4px !important; border: none !important;
  min-height: 0 !important; margin-bottom: 10px; }
.kct-app .kct-tabs .lm-TabBar-content, .kct-app .kct-tabs .p-TabBar-content { border: none !important; gap: 4px; }
.kct-app .kct-tabs .lm-TabBar-tab, .kct-app .kct-tabs .p-TabBar-tab {
  background: transparent !important; border: none !important; border-radius: 9px !important;
  color: #6B7280 !important; font-weight: 600; font-size: 13px; padding: 7px 16px !important;
  margin: 0 !important; min-width: 0 !important; flex: 0 0 auto !important; line-height: 1.4 !important;
  height: auto !important; transition: all .15s; }
.kct-app .kct-tabs .lm-TabBar-tab:hover, .kct-app .kct-tabs .p-TabBar-tab:hover { color: """ + ORANGE + """ !important; }
.kct-app .kct-tabs .lm-TabBar-tab.lm-mod-current, .kct-app .kct-tabs .p-TabBar-tab.p-mod-current {
  background: #FFFFFF !important; color: """ + NAVY + """ !important;
  box-shadow: 0 1px 3px rgba(0,0,0,.12), 0 1px 2px rgba(0,0,0,.06); }
.kct-app .kct-tabs .lm-TabBar-tab::before, .kct-app .kct-tabs .p-TabBar-tab::before { display: none !important; }
.kct-app .kct-tabs > .lm-TabPanel-stackedPanel, .kct-app .kct-tabs > .p-TabPanel-stackedPanel,
.kct-app .kct-tabs .widget-tab-contents {
  border: 1px solid #E5E7EB !important; border-radius: 14px !important; padding: 16px !important;
  background: #FFFFFF; box-shadow: 0 1px 2px rgba(0,0,0,.04); }
.kct-app .kct-panel { gap: 10px; }
.kct-app .kct-section { font-weight: 700; color: """ + NAVY + """; margin-top: 6px; display: flex; gap: 8px; align-items: center; }
/* buttons */
.kct-app .kct-btn {
  border-radius: 9px !important; font-weight: 600 !important; font-size: 13px !important; height: 36px !important;
  padding: 0 16px !important; width: auto !important; min-width: 0 !important; border: 1px solid #D1D5DB !important;
  background: #FFFFFF !important; color: #111827 !important; box-shadow: none !important; transition: all .15s; }
.kct-app .kct-btn:hover { background: #F9FAFB !important; border-color: #9CA3AF !important; }
.kct-app .kct-btn-primary { background: """ + ORANGE + """ !important; border-color: """ + ORANGE + """ !important;
  color: #FFFFFF !important; }
.kct-app .kct-btn-primary:hover { background: """ + ORANGE_DARK + """ !important; border-color: """ + ORANGE_DARK + """ !important; }
.kct-app .kct-btn-next { background: """ + NAVY + """ !important; border-color: """ + NAVY + """ !important;
  color: #FFFFFF !important; }
.kct-app .kct-btn-next:hover { background: #1A1A80 !important; }
.kct-app .kct-btn:focus { outline: none !important; box-shadow: 0 0 0 3px rgba(255,98,0,.25) !important; }
/* text inputs and dropdowns */
.kct-app .kct-input input, .kct-app .kct-select select {
  border-radius: 9px !important; border: 1px solid #D1D5DB !important; background-color: #F9FAFB !important;
  padding: 0 12px !important; height: 36px !important; font-size: 13px !important; color: #111827 !important; }
.kct-app .kct-input input:focus, .kct-app .kct-select select:focus {
  outline: none !important; border-color: """ + ORANGE + """ !important; box-shadow: 0 0 0 3px rgba(255,98,0,.20) !important;
  background: #FFFFFF !important; }
.kct-app .kct-input, .kct-app .kct-select { height: auto !important; }
/* dropdowns: a clear arrow on the right */
.kct-app .kct-select select { -webkit-appearance: none !important; -moz-appearance: none !important; appearance: none !important;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23FF6200' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E") !important;
  background-repeat: no-repeat !important; background-position: right 12px center !important;
  background-size: 18px !important; padding-right: 40px !important; font-weight: 500; }
.kct-app .kct-select select:hover { border-color: #FF6200 !important; }
.kct-app .kct-empty { display: flex; gap: 14px; align-items: center; justify-content: center; min-height: 110px;
  border: 2px dashed #E5E7EB; border-radius: 14px; color: #4B5563; padding: 16px; }
.kct-app .widget-hbox { gap: 8px; align-items: center; }
.kct-app .kct-hint { color: #4B5563; font-size: 13px; }
/* hand cursor on everything clickable; text cursor stays in text fields */
.kct-app .kct-tabs .lm-TabBar-tab, .kct-app .kct-tabs .p-TabBar-tab, .kct-app .kct-btn, .kct-app .kct-btn *,
.kct-app .kct-select select, .kct-app input[type=checkbox], .kct-app input[type=file], .kct-app label.widget-upload,
.kct-app .jupyter-button { cursor: pointer !important; }
.kct-app .kct-input input { cursor: text !important; }
.kct-app .kct-btn:disabled, .kct-app .jupyter-button:disabled { cursor: not-allowed !important; opacity: .55; }
/* parts of later releases: greyed out, marked "coming soon" */
.kct-app .kct-soon-from-3 .lm-TabBar-tab:nth-child(n+3):not(:last-child),
.kct-app .kct-soon-from-3 .p-TabBar-tab:nth-child(n+3):not(:last-child),
.kct-app .kct-soon-from-4 .lm-TabBar-tab:nth-child(n+4):not(:last-child),
.kct-app .kct-soon-from-4 .p-TabBar-tab:nth-child(n+4):not(:last-child) {
  color: #B0B5BD !important; font-style: italic; }
.kct-app .kct-soon-card { min-height: 200px; display: flex; flex-direction: column; align-items: center;
  justify-content: center; text-align: center; border: 2px dashed #E5E7EB; border-radius: 14px; color: #6B7280; }
.kct-app .kct-soon-badge { display: inline-block; background: #F3F4F6; color: #6B7280; border-radius: 999px;
  padding: 2px 10px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; font-style: normal; }
.kct-app .kct-soon-text { color: #9CA3AF !important; }
</style>
"""


TAB_ICONS = {"1 Case": "📁", "2 Test steps": "📋", "3 Evidence": "📎", "4 Assess": "⚖️", "5 Result": "✅",
             "History": "🕘"}
NEW_CASE = "+new"   # the "+ New case" entry of the case list

FAKE_STEPS = ("Fake AI: these test steps are fixed sample answers, not read from your files. "
              'For your own documents set MODE = "live" in the first cell and run all cells again.')


def _uploads(value) -> List[tuple]:
    """(name, bytes) for each uploaded file; FileUpload's value differs between ipywidgets 7 and 8."""
    if isinstance(value, dict):  # ipywidgets 7: {name: {"content": bytes, ...}}
        return [(name, bytes(item["content"])) for name, item in value.items()]
    return [(item["name"], bytes(item["content"])) for item in value or ()]


class KctApp:
    def __init__(self, kct, title: str = "Key Control Testing") -> None:
        import ipywidgets as w

        self.kct = kct
        self.w = w
        self.case: Optional[str] = None
        self.interpretation_id: Optional[str] = None   # the test steps this session works with
        self._opening = False
        self.titles: List[str] = []
        self.next_buttons: List = []
        panels = []

        # header: case picker
        self.case_picker = w.Dropdown(description="Case", layout=w.Layout(width="60%"), style={"description_width": "initial"})
        self.case_picker.observe(lambda change: self._case_changed(change["new"]), names="value")
        self.refresh_button = w.Button(description="Refresh", icon="refresh")
        self.refresh_button.on_click(lambda _: self.refresh_cases())
        self._style(self.case_picker, self.refresh_button)
        header_row = [self.case_picker, self.refresh_button]
        header_row.append(self._soon_button("Run all", "forward", "Tabs 2 to 5 in one click"))

        # 1 Case
        self.case_out = w.Output()
        self.new_name = w.Text(placeholder="Name of the control, e.g. CTL-IAM-0472 Password resets",
                               layout=w.Layout(width="60%"))
        self.create_button = w.Button(description="Create case", icon="plus")
        self.create_button.on_click(lambda _: self._safe(self.case_out, self._create_clicked))
        self.cd_upload = w.FileUpload(accept=".pdf", multiple=False, description="Control details")
        self.tp_upload = w.FileUpload(accept=".pdf", multiple=False, description="Test plan")
        self._style(self.new_name, primary=[self.create_button])
        self.new_box = w.VBox([
            w.HTML(f"<div class='kct-section'>{show.svg('folder-plus')} New case</div>"
                   "<div class='kct-hint'>Give it a name; its documents come with each run.</div>"),
            w.HBox([self.new_name, self.create_button]),
            w.HTML("<div class='kct-section kct-soon-text'>Import the control folder from SharePoint (ZIP or folder) "
                   "<span class='kct-soon-badge'>coming soon</span></div>"),
            self._soon_button("Import ZIP", "upload", "Upload the SharePoint control folder as a ZIP")])
        # an existing case: its documents, and a new run (case interpretation) of it
        self.case_info = w.Output()
        self.rerun_button = w.Button(description="Make test steps", icon="list",
                                     tooltip="A new run (case interpretation) of this case")
        self.rerun_button.on_click(lambda _: self._safe(self.case_out, self._run_clicked))
        self._style(self.cd_upload, self.tp_upload, primary=[self.rerun_button])
        self.case_box = w.VBox([
            self.case_info,
            w.HTML(f"<div class='kct-section'>{show.svg('play')} New run (case interpretation)</div>"
                   "<div class='kct-hint'>Choose the control details and the test plan (PDF) for this run, then "
                   "<b>Make test steps</b>. Without new files the run uses the documents of the last run.</div>"),
            w.HBox([self.cd_upload, self.tp_upload, self.rerun_button])], layout=w.Layout(display="none"))
        self.pick_hint = w.HTML(
            f"<div class='kct-empty'>{show.svg('pointer', size=28)}<div><b>Click the Case list at the top</b> and "
            "select a case, or <b>+ New case</b> to add one.</div></div>")
        panels.append(("1 Case", [self.pick_hint, self.new_box, self.case_box, self.case_out]))

        # 2 Test steps
        self.interpret_button = w.Button(description="Make test steps", icon="list")
        self.interpret_button.on_click(lambda _: self._safe(self.steps_out, self.interpret))
        self.latest_button = w.Button(description="Show latest", icon="eye")
        self.latest_button.on_click(lambda _: self._safe(self.steps_out, self.show_steps))
        self.step_picker = w.Dropdown(description="Step", layout=w.Layout(width="70%"), style={"description_width": "initial"})
        self.step_picker.observe(lambda change: self._step_changed(change["new"]), names="value")
        self.steps_out = w.Output()
        self.step_out = w.Output()
        self._style(self.latest_button, self.step_picker, primary=[self.interpret_button])
        panels.append(("2 Test steps", [
            w.HTML("<div class='kct-hint'>The AI reads the case's control details and test plan and writes the "
                   "test steps, each with the criteria it must meet.</div>"),
            w.HBox([self.interpret_button, self.latest_button]), self.steps_out, self.step_picker, self.step_out]))

        # tabs of later releases: shown greyed out, with what they will do
        soon = []
        soon.append(("3 Evidence", "Upload the evidence of the case and see how big files are split for the AI."))
        soon.append(("4 Assess", "Check every piece of evidence against every test step, with a live progress bar."))
        soon.append(("5 Result", "The verdict of every test step, with its exceptions and a read-only PDF report."))
        self.available = [name for name, _ in panels]

        # History: earlier runs, to look at (or continue with) without running the AI again
        self.history_picker = w.Dropdown(description="Run", layout=w.Layout(width="80%"),
                                         style={"description_width": "initial"})
        self.history_picker.observe(lambda change: self._history_picked(change["new"]), names="value")
        self.history_all = w.Checkbox(value=False, description="All cases", indent=False,
                                      layout=w.Layout(width="auto"))
        self.history_all.observe(lambda change: self._safe(self.history_out, self.history), names="value")
        self.history_refresh = w.Button(description="Refresh", icon="refresh")
        self.history_refresh.on_click(lambda _: self._safe(self.history_out, self.history))
        self.use_button = w.Button(description="Continue with these test steps", icon="check")
        self.use_button.on_click(lambda _: self._safe(self.history_out, self.use_run, self.history_picker.value))
        self.history_out = w.Output()
        self.history_step_picker = w.Dropdown(description="Step", layout=w.Layout(width="70%"),
                                              style={"description_width": "initial"})
        self.history_step_picker.observe(lambda change: self._history_step(change["new"]), names="value")
        self.history_step_out = w.Output()
        self._style(self.history_picker, self.history_refresh, self.history_step_picker, primary=[self.use_button])
        history_panel = w.VBox([
            w.HTML("<div class='kct-hint'>The earlier runs (case interpretations) of the case chosen at the top, "
                   "newest first; tick <b>All cases</b> for every case. For each: its documents and test steps"
                   ". Nothing is sent to the AI here.</div>"),
            w.HBox([self.history_picker, self.history_all, self.history_refresh]), self.use_button, self.history_out,
            self.history_step_picker, self.history_step_out])
        history_panel.add_class("kct-panel")

        # tabs, each with a "Next" button (hidden until its step is done) except the last one available
        children = []
        for index, (name, items) in enumerate(panels):
            if index + 1 < len(panels):
                button = w.Button(description=f"Next: {panels[index + 1][0][2:]}", icon="arrow-right",
                                  layout=w.Layout(display="none"))
                button.on_click(lambda _, target=index + 1: self.go(target))
                button.add_class("kct-btn")
                button.add_class("kct-btn-next")
                self.next_buttons.append(button)
                items = items + [button]
            panel = w.VBox(items)
            panel.add_class("kct-panel")
            children.append(panel)
            self.titles.append(name)
        for name, text in soon:
            panel = w.VBox([w.HTML(
                f"<div class='kct-soon-card'><div class='kct-soon-badge'>coming soon</div>"
                f"<div style='font-size:16px;font-weight:700;margin-top:10px'>{name[2:]}</div>"
                f"<div class='kct-hint' style='margin-top:4px'>{text}</div></div>")])
            panel.add_class("kct-panel")
            children.append(panel)
            self.titles.append(f"{name} · soon")
        children.append(history_panel)
        self.titles.append("History")
        self.tabs = w.Tab(children=children)
        self.tabs.add_class("kct-tabs")
        if soon:
            self.tabs.add_class(f"kct-soon-from-{len(panels) + 1}")
        for index, name in enumerate(self.titles):
            self.tabs.set_title(index, f"{TAB_ICONS.get(name.split(' · ')[0], '')} {name}".strip())

        config = self._settings()
        subtitle = "From the control details and the test plan to test steps"
        self.header = w.VBox([
            w.HTML(STYLE),
            w.HTML(show.banner(title, subtitle).data),
            w.HTML(show.mode(config.ai_provider, config.ai_model).data),
            w.HBox(header_row)])
        self.widget = w.VBox([self.header, self.tabs])
        self.widget.add_class("kct-app")
        self.refresh_cases()
        self._safe(self.history_out, self.history)

    # --- showing the app ----------------------------------------------------------------

    def _ipython_display_(self) -> None:
        from IPython.display import display

        display(self.widget)

    # --- actions (called by the buttons, usable from code) ----------------------------------

    def refresh_cases(self, select: Optional[str] = None) -> List[str]:
        cases = self.kct.files.case_ids()
        names = self._case_names()
        options = [(names[c] if names[c] == c else f"{names[c]}  ({c})", c) for c in cases]
        current = select or self.case
        self._opening_list = True
        try:
            self.case_picker.options = [("Click here and select a case …", None), ("+ New case", NEW_CASE)] + options
        finally:
            self._opening_list = False
        self.case_picker.value = current if current in cases else None
        return cases

    def set_documents(self, control_details: tuple, test_plan: tuple) -> None:
        """The control details and the test plan, each (name, bytes), for the next run of the current case."""
        from services.control_testing.data import DocumentKind
        from services.files.file_service import UploadedFile

        case = self._need_case()
        self.kct.files.replace_documents(case, {
            DocumentKind.CONTROL_DETAILS: [UploadedFile(name=control_details[0], data=control_details[1])],
            DocumentKind.TEST_PLAN: [UploadedFile(name=test_plan[0], data=test_plan[1])]})
        self._case_card(case)

    def new_run(self, control_details: Optional[tuple] = None, test_plan: Optional[tuple] = None):
        """A new run (case interpretation) of the current case; with files, they replace the last run's."""
        self._need_case()
        if control_details or test_plan:
            if not (control_details and test_plan):
                raise ValueError("Choose both files for the run: the control details and the test plan.")
            self.set_documents(control_details, test_plan)
        self.go(1)
        return self.interpret()

    def go(self, index: int) -> None:
        """Open a tab (0 = the first)."""
        self.tabs.selected_index = index

    def create_case(self, name: str) -> str:
        """A new case with only a name; its documents come with each run (tab 1, after picking it)."""
        case = self.kct.files.create_case(name)
        self._open_fresh(case)
        self._show(self.case_out, show.notice(
            f"Case {name.strip()} created. Now choose its control details and test plan above, then Make test steps.",
            "ok"))
        self.new_name.value = ""
        return case

    def interpret(self):
        case = self._need_case()
        self.step_out.clear_output()
        from services.control_testing.data import DocumentKind
        from services.files.exceptions import CaseNotFoundError

        try:
            for kind in (DocumentKind.CONTROL_DETAILS, DocumentKind.TEST_PLAN):
                self.kct.files.document_names(case, kind)
        except CaseNotFoundError:
            raise ValueError("This case has no documents yet: choose the control details and the test plan in "
                             "tab 1, then Make test steps.") from None
        with self._busy(self.steps_out, f"Reading the control details and test plan of {self._case_names().get(case, case)} …",
                        self.interpret_button, self.rerun_button):
            interpretation = self.kct.interpretations.generate(case)
        self.kct.files.record_run(case, interpretation.metadata.case_interpretation_id)
        self._render_steps(interpretation)
        return interpretation

    def show_steps(self):
        from services.database.exceptions import RecordNotFoundError

        case = self._need_case()
        try:
            interpretation = self.kct.database.latest_interpretation(case)
        except RecordNotFoundError:
            self._show(self.steps_out, show.notice("No test steps for this case yet: click 'Make test steps'.", "warn"))
            return None
        self._render_steps(interpretation)
        return interpretation

    def history(self) -> list:
        """The earlier runs (case interpretations) of the current case, or of all cases; newest first."""
        if not self.history_all.value and not self.case:
            runs = []
        else:
            runs = self.kct.database.interpretations(None if self.history_all.value else self.case)
        names = self._case_names()
        self.history_picker.options = [
            ("Click here and select a run …" if runs else
             "No runs yet" + ("" if self.history_all.value else " for this case"), None)] + [
            (f"{m.created_at[:16].replace('T', ' ')} · {names.get(m.case_reference, m.case_reference)} · "
             f"{m.step_count} test steps · {m.model}", m.case_interpretation_id) for m in runs]
        self.history_picker.value = None
        self.use_button.disabled = True
        if not runs:
            self._show(self.history_out, show.notice(self._history_hint(
                "No runs yet." if self.history_all.value or not self.case else
                f"No runs yet for {self._case_names().get(self.case, self.case)}: make test steps in tab 2."), "info"))
        return runs

    def show_history(self, interpretation_id: str):
        """One earlier run: its documents, test steps and what came out of it."""
        from IPython.display import display
        from services.control_testing.data import DocumentKind

        interpretation = self.kct.database.find_interpretation(interpretation_id)
        meta = interpretation.metadata
        case = meta.case_reference
        recorded = self.kct.files.run_documents(case, interpretation_id)
        documents = "".join(
            f"<div>{show.svg('file')} {show.escape(d['name'])} <span style='color:{show.GREY}'>"
            f"({d['kind'].replace('_', ' ')}) · SHA-256 {d['sha256'][:12]}…</span></div>" for d in recorded)
        if not recorded:   # runs made before the documents were recorded
            from services.files.exceptions import CaseNotFoundError

            try:
                documents = "".join(
                    f"<div>{show.svg('file')} {show.escape(n)} <span style='color:{show.GREY}'>({label}, now)</span></div>"
                    for kind, label in ((DocumentKind.CONTROL_DETAILS, "control details"),
                                        (DocumentKind.TEST_PLAN, "test plan"))
                    for n in self.kct.files.document_names(case, kind))
            except CaseNotFoundError:
                documents = ""
        header = show._html(
            f"<div style='{show.CARD}'><div style='font-weight:700;margin-bottom:4px'>"
            f"{show.svg('clock')} {show.escape(self._case_names().get(case, case))}</div>"
            f"<div style='color:{show.GREY}'>{show.escape(meta.created_at[:19].replace('T', ' '))} · "
            f"{show.escape(meta.provider)} / {show.escape(meta.model)} · run {show.escape(meta.case_interpretation_id)}"
            f"</div><div style='margin-top:8px'><div style='color:{show.GREY};font-size:12px'>Documents this run read:"
            f"</div>{documents or '<i>not recorded</i>'}</div></div>")
        with self.history_out:
            self.history_out.clear_output()
            if self.kct.database.__class__.__name__.lower().startswith("memory"):
                display(show.notice(self._history_hint(""), "warn"))
            display(header)
            display(show.test_steps(interpretation))
        self._history_steps = {s.id: s for s in interpretation.test_steps}
        self.history_step_picker.options = [(f"{s.reference}: {s.title}", s.id) for s in interpretation.test_steps]
        if interpretation.test_steps:
            self.history_step_picker.value = interpretation.test_steps[0].id
            self._history_step(interpretation.test_steps[0].id)
        return interpretation

    def use_run(self, interpretation_id: str):
        """Continue with an earlier run: its case and test steps become the current ones (no AI call)."""
        interpretation = self.kct.database.find_interpretation(interpretation_id)
        self._open_fresh(interpretation.metadata.case_reference)
        self._render_steps(interpretation)
        self.go(1)
        return interpretation

    # --- internals -------------------------------------------------------------------------

    def _create_clicked(self) -> None:
        if not self.new_name.value.strip():
            self._show(self.case_out, show.notice("Type a name for the case first.", "warn"))
            return
        self.create_case(self.new_name.value)

    def _run_clicked(self) -> None:
        control_details, test_plan = _uploads(self.cd_upload.value), _uploads(self.tp_upload.value)
        self.new_run(control_details[0] if control_details else None, test_plan[0] if test_plan else None)

    def _open_fresh(self, case: str) -> None:
        """After an upload: a new run. Nothing of earlier runs is shown (test steps, results)."""
        self._opening = True
        try:
            self.refresh_cases(select=case)
        finally:
            self._opening = False
        self._open(case, fresh=True)

    def _case_changed(self, case: Optional[str]) -> None:
        if getattr(self, "_opening_list", False):
            return
        if not self._opening:            # picked at the top (or the app just opened)
            self._open(case, fresh=False)

    def _open(self, case: Optional[str], fresh: bool) -> None:
        picked = case not in (None, NEW_CASE)
        self.pick_hint.layout.display = "" if case is None else "none"
        self.new_box.layout.display = "" if case == NEW_CASE else "none"
        self.case_box.layout.display = "" if picked else "none"
        case = case if picked else None
        self.case = case
        self.interpretation_id = None
        self._steps = {}
        for out in self._outputs():
            out.clear_output()
        for button in self.next_buttons:
            button.layout.display = "none"
        self.step_picker.options = [("No test steps yet: click Make test steps", None)]
        if hasattr(self, "history_all"):
            self.history_out.clear_output()
            self.history_step_out.clear_output()
            self._safe(self.history_out, self.history)
        if not case:
            return
        self._safe(self.case_out, self._case_card, case)
        # every run starts clean: earlier test steps and results stay saved, but are not shown
        self._show(self.steps_out, show.notice(
            "New run: click 'Make test steps'." if fresh else
            "Click 'Make test steps' for a new run, or 'Show latest' to continue with the last saved test steps.",
            "info"))

    def _outputs(self) -> list:
        return [self.case_out, self.case_info, self.steps_out, self.step_out]

    def _ready(self, index: int) -> None:
        """Step `index` is done: show its "Next" button (the last tab has none)."""
        if index < len(self.next_buttons):
            self.next_buttons[index].layout.display = ""

    def _render_steps(self, interpretation) -> None:
        from IPython.display import display

        with self.steps_out:
            self.steps_out.clear_output()
            if self._fake():
                display(show.notice(FAKE_STEPS, "warn"))
            display(show.test_steps(interpretation))
        self._steps = {s.id: s for s in interpretation.test_steps}
        self.interpretation_id = interpretation.metadata.case_interpretation_id
        self._safe(self.history_out, self.history)
        self.step_picker.options = [(f"{s.reference}: {s.title}", s.id) for s in interpretation.test_steps]
        if interpretation.test_steps:                 # the first step's details are shown right away
            self.step_picker.value = interpretation.test_steps[0].id
            self._step_changed(interpretation.test_steps[0].id)
        self._ready(1)

    def _case_card(self, case: str) -> None:
        """Tab 1 for a picked case: its name and the documents of its last run."""
        from services.control_testing.data import DocumentKind
        from services.files.exceptions import CaseNotFoundError

        rows = []
        for kind, label in ((DocumentKind.CONTROL_DETAILS, "control details"), (DocumentKind.TEST_PLAN, "test plan")):
            try:
                rows += [f"<div>{show.svg('file')} {show.escape(n)} <span style='color:{show.GREY}'>({label})</span></div>"
                         for n in self.kct.files.document_names(case, kind)]
            except CaseNotFoundError:
                pass
        documents = "".join(rows) or f"<div style='color:{show.GREY}'><i>No documents yet: choose them below.</i></div>"
        runs = len(self.kct.database.interpretations(case))
        self._show(self.case_info, show._html(
            f"<div style='{show.CARD}'><div style='font-weight:700;margin-bottom:6px;font-size:15px'>"
            f"{show.svg('folder')} {show.escape(self._case_names().get(case, case))}"
            f" <span style='color:{show.GREY};font-weight:400;font-size:12px'>{show.escape(case)}</span></div>"
            f"<div style='color:{show.GREY};font-size:12px;margin-bottom:4px'>Documents"
            f"{' of the last run' if runs else ''}:</div>{documents}"
            f"<div style='color:{show.GREY};margin-top:8px'>{show.svg('clock')} {runs} earlier run(s); see History.</div>"
            f"</div>"))
        if runs:
            self._ready(0)

    def _history_picked(self, run: Optional[str]) -> None:
        self.use_button.disabled = not run
        self.history_step_out.clear_output()
        if run:
            self._safe(self.history_out, self.show_history, run)
        else:
            self.history_out.clear_output()
            self.history_step_picker.options = [("Select a run above first", None)]

    def _history_step(self, step_id: Optional[str]) -> None:
        if step_id and step_id in getattr(self, "_history_steps", {}):
            self._show(self.history_step_out, show.criteria(self._history_steps[step_id]))

    def _history_hint(self, text: str) -> str:
        if self._settings().db_driver == "memory":
            return (text + " The database is in memory: runs are lost when the kernel restarts. "
                    "Set KCT_DB_DRIVER=sqlite in .env to keep them.").strip()
        return text

    def _case_names(self) -> dict:
        return {c: self.kct.files.case_name(c) for c in self.kct.files.case_ids()}

    def _fake(self) -> bool:
        return self._settings().ai_provider == "fake"

    def _step_changed(self, step_id: Optional[str]) -> None:
        if step_id and step_id in getattr(self, "_steps", {}):
            self._show(self.step_out, show.criteria(self._steps[step_id]))

    def _soon_button(self, description: str, icon: str, what: str):
        """A greyed-out button for something a later release brings."""
        button = self.w.Button(description=f"{description} · soon", icon=icon, disabled=True,
                               tooltip=f"Coming soon: {what}")
        self._style(button)
        return button

    @contextmanager
    def _busy(self, out, text: str, *buttons):
        """While work runs: the buttons are disabled with a spinner, `out` shows a loader (skipped if None)."""
        icons = [button.icon for button in buttons]
        for button in buttons:
            button.disabled, button.icon = True, "spinner fa-spin"
        if out is not None:
            self._show(out, show.loading(text))
        try:
            yield
        finally:
            for button, icon in zip(buttons, icons):
                button.disabled, button.icon = False, icon

    def _need_case(self) -> str:
        if not self.case:
            raise ValueError("No case chosen: create or pick one in tab 1 first.")
        return self.case

    def _show(self, out, block) -> None:
        from IPython.display import display

        with out:
            out.clear_output()
            display(block)

    def _safe(self, out, action, *args):
        """Run an action; show a readable error instead of a traceback when it fails."""
        try:
            return action(*args)
        except Exception as exc:  # shown in the app, also logged
            import logging

            logging.getLogger("kct").error("app: %s failed: %s\n%s", getattr(action, "__name__", action), exc,
                                           traceback.format_exc())
            self._show(out, show.notice(f"{type(exc).__name__}: {exc}", "error"))
            return None

    def _style(self, *widgets, primary=()) -> None:
        """Flowbite-like classes: inputs, dropdowns, buttons (primary = orange)."""
        w = self.w
        for widget in widgets:
            if isinstance(widget, (w.Button, w.FileUpload)):
                widget.add_class("kct-btn")
            elif isinstance(widget, w.Dropdown):
                widget.add_class("kct-select")
            else:
                widget.add_class("kct-input")
        for widget in primary:
            widget.add_class("kct-btn")
            widget.add_class("kct-btn-primary")

    @staticmethod
    def _settings():
        from services.config import settings

        return settings()
