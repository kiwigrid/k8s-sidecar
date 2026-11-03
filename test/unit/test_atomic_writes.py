"""Readers must never observe a partially published ConfigMap/Secret file."""
import errno
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.argv = [sys.argv[0]]  # helpers parses command-line options at import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
import helpers


class AtomicWriteTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.folder = Path(self.directory.name)
        self.target = self.folder / 'rules.yaml'
        self.environment = patch.dict(os.environ)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        os.environ.pop('DEFAULT_FILE_MODE', None)

    def write(self, data, data_type=helpers.CONTENT_TYPE_TEXT):
        return helpers.write_data_to_file(str(self.folder), self.target.name, data, data_type)

    def assert_no_temporary_files(self):
        self.assertEqual(list(self.folder.glob('.k8s-sidecar-*')), [])

    def test_text_binary_and_empty_content(self):
        for value, kind, expected in [('Grüße 世界', 'ascii', 'Grüße 世界'.encode()),
                                      (b'\x00\xff\x80', 'binary', b'\x00\xff\x80'),
                                      ('', 'ascii', b'')]:
            with self.subTest(kind=kind, value=value):
                self.assertTrue(self.write(value, kind))
                self.assertEqual(self.target.read_bytes(), expected)
                self.assert_no_temporary_files()

    def test_unchanged_content_keeps_inode_and_mtime(self):
        self.write('same')
        before = self.target.stat()
        with patch.object(helpers.os, 'replace') as replace:
            self.assertFalse(self.write('same'))
        replace.assert_not_called()
        after = self.target.stat()
        self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))

    def test_new_file_respects_umask(self):
        previous = os.umask(0o027)
        try:
            self.write('new')
        finally:
            os.umask(previous)
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o640)

    def test_existing_permissions_and_ownership_are_preserved(self):
        self.target.write_text('old')
        self.target.chmod(0o640)
        before = self.target.stat()
        self.write('new')
        after = self.target.stat()
        self.assertEqual(stat.S_IMODE(after.st_mode), 0o640)
        self.assertEqual((after.st_uid, after.st_gid), (before.st_uid, before.st_gid))

    def test_explicit_mode_is_set_before_publication(self):
        os.environ['DEFAULT_FILE_MODE'] = '440'
        real_replace = os.replace

        def replace(source, destination):
            self.assertEqual(stat.S_IMODE(os.stat(source).st_mode), 0o440)
            real_replace(source, destination)

        with patch.object(helpers.os, 'replace', side_effect=replace):
            self.write('new')
            self.write('updated')
        self.assertEqual(stat.S_IMODE(self.target.stat().st_mode), 0o440)

    def test_write_failure_preserves_old_file_and_cleans_up(self):
        self.target.write_text('old')
        real_fdopen = os.fdopen

        class FailingWriter:
            def __init__(self, fd, mode):
                self.file = real_fdopen(fd, mode)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.file.close()

            def fileno(self):
                return self.file.fileno()

            def write(self, data):
                self.file.write(data[:2])
                self.file.flush()
                raise OSError(errno.ENOSPC, 'disk full')

        with patch.object(helpers.os, 'fdopen', side_effect=FailingWriter):
            with self.assertRaises(OSError):
                self.write('new contents')
        self.assertEqual(self.target.read_text(), 'old')
        self.assert_no_temporary_files()

    def test_sync_and_replace_failures_preserve_old_file(self):
        for operation in ['fsync', 'replace']:
            with self.subTest(operation=operation):
                self.target.write_text('old')
                with patch.object(helpers.os, operation, side_effect=OSError(errno.EIO, 'I/O failure')):
                    with self.assertRaises(OSError):
                        self.write('new')
                self.assertEqual(self.target.read_text(), 'old')
                self.assert_no_temporary_files()

    def test_failed_creation_leaves_no_destination(self):
        with patch.object(helpers.os, 'replace', side_effect=OSError(errno.EIO, 'I/O failure')):
            with self.assertRaises(OSError):
                self.write('new')
        self.assertFalse(self.target.exists())
        self.assert_no_temporary_files()

    def test_symlink_is_preserved_and_target_is_updated(self):
        elsewhere = self.folder / 'elsewhere'
        elsewhere.mkdir()
        real_target = elsewhere / 'actual.yaml'
        for existing in [False, True]:
            with self.subTest(existing=existing):
                if existing:
                    real_target.write_text('old')
                self.target.symlink_to('elsewhere/actual.yaml')
                self.write('new')
                self.assertTrue(self.target.is_symlink())
                self.assertEqual(real_target.read_text(), 'new')
                self.assertEqual(list(elsewhere.glob('.k8s-sidecar-*')), [])
                self.target.unlink()
                real_target.unlink()

    def test_reader_sees_old_file_until_complete_replacement(self):
        old, new = 'old\n' * 10000, 'new\n' * 10000
        self.target.write_text(old)
        ready, release = threading.Event(), threading.Event()
        errors = []
        real_open, real_fdopen = open, os.fdopen

        class PausedWriter:
            def __init__(self, file):
                self.file = file

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.file.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self.file, name)

            def write(self, data):
                middle = len(data) // 2
                self.file.write(data[:middle])
                self.file.flush()
                ready.set()
                if not release.wait(5):
                    raise TimeoutError('reader did not finish')
                self.file.write(data[middle:])

        def open_file(path, mode='r', **kwargs):
            file = real_open(path, mode, **kwargs)
            return PausedWriter(file) if 'w' in mode else file

        def writer():
            try:
                self.write(new)
            except BaseException as error:
                errors.append(error)

        with self.target.open() as existing_reader:
            with patch.object(helpers, 'open', side_effect=open_file, create=True), \
                    patch.object(helpers.os, 'fdopen', side_effect=lambda fd, mode: PausedWriter(real_fdopen(fd, mode))):
                thread = threading.Thread(target=writer)
                thread.start()
                try:
                    self.assertTrue(ready.wait(5))
                    for _ in range(50):
                        self.assertEqual(self.target.read_text(), old)
                finally:
                    release.set()
                    thread.join(5)
                self.assertFalse(thread.is_alive())
            self.assertEqual(existing_reader.read(), old)
        self.assertEqual(errors, [])
        self.assertEqual(self.target.read_text(), new)
        self.assert_no_temporary_files()


if __name__ == '__main__':
    unittest.main()
