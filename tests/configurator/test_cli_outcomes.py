"""Selection uncertainty and private recovery have explicit stable CLI outcomes."""
import io,sys,tempfile,unittest
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
from unittest.mock import patch
from configurator.__main__ import report_result
from configurator import handoff_cli
from configurator.selection import UncertainSelection,Selection

class CliOutcomeTests(unittest.TestCase):
    def test_kept_private_draft_is_success_without_native_save_or_activation_claim(self):
        output=io.StringIO()
        with redirect_stdout(output):code=report_result(('draft','/private/draft'))
        self.assertEqual(code,0);self.assertIn('no native scene saved',output.getvalue())
        self.assertIn('Nothing activated',output.getvalue())

    def test_uncertain_selection_cli_is_five_without_success_or_rollback(self):
        output=io.StringIO();errors=io.StringIO()
        with tempfile.TemporaryDirectory() as root:
            exception=UncertainSelection('verification failed');exception.add_note('Inspect before retrying.')
            before=Selection(None,None)
            with patch.object(sys,'argv',['handoff','--root',root,'--use-legacy','--expect-selected','legacy']),patch.object(handoff_cli,'inspect_selection',return_value=before),patch.object(handoff_cli,'select_revision',side_effect=exception),redirect_stdout(output),redirect_stderr(errors):
                code=handoff_cli.main()
        self.assertEqual(code,5);self.assertEqual(output.getvalue(),'')
        self.assertIn('Selection outcome uncertain',errors.getvalue());self.assertIn('Inspect before retrying',errors.getvalue())
