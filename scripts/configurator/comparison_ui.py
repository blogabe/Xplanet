"""Review the complete bounded framing set before any renderer is invoked."""
from textual.containers import Horizontal,VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Static,Select,Label
from datetime import datetime,timezone
from .comparison import plan as comparison_plan
from .model import MONTHS

class ComparisonReview(ModalScreen[bool]):
    DEFAULT_CSS='''
    ComparisonReview { align: center middle; }
    ComparisonReview > VerticalScroll { width: 80; max-width: 95%; height: auto; max-height: 90%; border: round $accent; padding: 1 2; background: $surface; }
    '''
    BINDINGS=[('escape','back','Back')]
    def __init__(self,plan):super().__init__();self.plan=plan
    def compose(self):
        with VerticalScroll():
            yield Static('Render three framing snapshots?')
            yield Static('Epoch: '+self.plan.epoch+'; each 1920×1080. Values: '+', '.join(self.plan.parameter+'='+str(getattr(view,self.plan.parameter)) for view in self.plan.views),markup=False)
            yield Static('60-second total render-process wait budget; cleanup/filesystem overhead is separate. At most three 16 MiB PNGs. Now is frozen once, without current-data captures. Static imagery is not historical imagery certification.')
            yield Static('Draft, ordinary previews, native files, selection and desktop remain unchanged. Open the local HTML contact sheet explicitly afterward; no browser opens automatically. Temporary originals disappear on editor exit; Export framing sheet can preserve an explicit durable copy.')
            with Horizontal():
                yield Button('Render set',id='comparison-confirm',variant='primary')
                yield Button('Back',id='comparison-back')
    def on_button_pressed(self,event):self.dismiss(event.button.id=='comparison-confirm')
    def action_back(self):self.dismiss(False)


class MonthComparisonReview(ModalScreen[object]):
    DEFAULT_CSS=ComparisonReview.DEFAULT_CSS.replace('ComparisonReview','MonthComparisonReview')
    BINDINGS=[('escape','back','Back')]
    def __init__(self,plan):super().__init__();self.plan=plan
    def compose(self):
        with VerticalScroll():
            yield Static('Compare three bundled imagery months?')
            yield Static('Family: '+self.plan.source.map_family+'; each 1920×1080. Camera and scene epoch held: '+self.plan.epoch,markup=False)
            yield Static('Only the day-map month changes. These are bundled 2004 textures, not three simulated seasons or certified historical imagery. No provider request or current-data relabeling.')
            for index,value in enumerate(self.plan.months,1):
                yield Label('Imagery month '+str(index))
                yield Select([(month,month) for month in MONTHS],value=value,allow_blank=False,id='comparison-month-'+str(index))
            yield Static('Same 60-second total render-process wait budget and three 16 MiB image bounds as framing sheets; cleanup overhead separate. Draft, ordinary previews and desktop unchanged.')
            yield Static('',id='month-comparison-error',markup=False)
            with Horizontal():
                yield Button('Render month set',id='month-comparison-confirm',variant='primary')
                yield Button('Back',id='month-comparison-back')
    def on_button_pressed(self,event):
        event.stop()
        if event.button.id!='month-comparison-confirm':self.action_back();return
        months=tuple(self.query_one('#comparison-month-'+str(i),Select).value for i in (1,2,3))
        try:result=comparison_plan(self.plan.source,kind='months',months=months,now=datetime.strptime(self.plan.epoch,'%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc))
        except ValueError as exc:self.query_one('#month-comparison-error',Static).update(str(exc));return
        self.dismiss(result)
    def action_back(self):self.dismiss(None)
