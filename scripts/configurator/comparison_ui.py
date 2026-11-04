"""Review the complete bounded framing set before any renderer is invoked."""
from textual.containers import Horizontal,VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button,Static

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
