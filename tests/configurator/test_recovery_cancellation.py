"""Owned recovery readers cooperate between chunks and unrelated entries."""
import os
import unittest
from unittest.mock import patch
from configurator import recovery
from configurator.owned_io import OwnedIO,CancelledIO
from tests.configurator.support_recovery import RecoveryFixture

class RecoveryCancellationTests(RecoveryFixture,unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_large_read_stops_between_chunks_and_keeps_bytes(self):
        path=self.root/'capture';raw=b'x'*(3*65536);path.write_bytes(raw);path.chmod(0o600)
        directory=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
        self.addCleanup(os.close,directory)
        io=OwnedIO();self.addCleanup(io.close);reads=[];original=os.read
        def read(fd,size):
            chunk=original(fd,size);reads.append(len(chunk));io.request_cancel();return chunk
        with patch('configurator.recovery.os.read',side_effect=read):
            with self.assertRaises(CancelledIO):await io.run(recovery.read,directory,path.name,len(raw))
        self.assertEqual(reads,[65536]);self.assertIsNone(io.owner)
        self.assertEqual(path.read_bytes(),raw)

    async def test_unknown_recovery_entries_are_cancellable_and_never_evicted(self):
        session=self.session();await session.checkpoint(*self.proposal());session.close()
        note=self.store.path/'private-note';note.write_bytes(b'preserve');before=note.read_bytes()
        with patch('configurator.recovery.io_checkpoint',side_effect=CancelledIO):
            with self.assertRaises(CancelledIO):self.store.entries()
        self.assertEqual(note.read_bytes(),before)
        self.assertTrue((self.store.path/session.identity).exists())

    async def test_directory_budget_counts_unrelated_entries_and_preserves_them(self):
        session=self.session();await session.checkpoint(*self.proposal());session.close()
        for index in range(3):(self.store.path/f'note-{index}').write_bytes(b'preserve')
        with patch.object(recovery,'ENTRY_LIMIT',2):
            with self.assertRaisesRegex(ValueError,'entry bound'):self.store.entries()
        self.assertEqual(len(list(self.store.path.glob('note-*'))),3)
        self.assertTrue((self.store.path/session.identity).exists())
