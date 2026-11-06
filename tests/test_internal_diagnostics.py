"""Unexpected failures retain bounded public-code identity, never secret values."""
import io,json
from contextlib import redirect_stdout,redirect_stderr
from types import SimpleNamespace
from unittest.mock import patch
from totalmarker.cli import main,internal_diagnostic
from .support import Sandbox

class InternalDiagnosticTests(Sandbox):
    def test_machine_contract_stays_generic_and_stderr_contains_only_type_and_code_location(self):
        secret='https://user:credential@private.invalid/path?token=secret'
        out=io.StringIO();err=io.StringIO()
        with patch('totalmarker.cli.load',return_value=SimpleNamespace(deferred_settings=())), patch('totalmarker.cli.run',side_effect=RuntimeError(secret)),redirect_stdout(out),redirect_stderr(err):
            code=main(['--root',str(self.root),'clouds'])
        self.assertEqual(code,2)
        self.assertEqual(json.loads(out.getvalue()),{'outcome':'failed','message':'Unexpected internal failure'})
        self.assertRegex(err.getvalue(),r'^Internal diagnostic: RuntimeError at totalmarker/cli\.py:[0-9]+\n$')
        for value in (secret,'credential','token=',str(self.root)):
            self.assertNotIn(value,out.getvalue()+err.getvalue())

    def test_external_exception_names_and_trace_paths_are_not_disclosed(self):
        secret=type('PrivateCredentialError',(Exception,),{})('secret message')
        text=internal_diagnostic(secret)
        self.assertEqual(text,'Internal diagnostic: Exception at unavailable')
        self.assertNotIn('PrivateCredential',text);self.assertNotIn('secret',text)

    def test_unavailable_diagnostic_sink_preserves_json_and_exit_two(self):
        class Broken:
            def __init__(self,error):self.error=error
            def write(self,text):raise self.error
        for sink in (None,Broken(OSError('closed descriptor')),Broken(ValueError('closed stream'))):
            with self.subTest(sink=type(sink).__name__):
                output=io.StringIO()
                with patch('totalmarker.cli.load',return_value=SimpleNamespace(deferred_settings=())),patch('totalmarker.cli.run',side_effect=RuntimeError('secret')),patch('sys.stderr',sink),redirect_stdout(output):
                    code=main(['--root',str(self.root),'clouds'])
                self.assertEqual(code,2)
                self.assertEqual(json.loads(output.getvalue()),{'outcome':'failed','message':'Unexpected internal failure'})
