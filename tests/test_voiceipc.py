from __future__ import annotations
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from assistant.technical.voiceipc import request,serve


class LocalIPCTests(unittest.TestCase):
    def test_idle_timeout_waits_for_active_request_then_stops(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'voice/control.sock';stopped=threading.Event()
            entered=threading.Event();release=threading.Event();replies=[]
            def handle(body):
                entered.set();release.wait(timeout=3);return {'text':'готово'}
            thread=threading.Thread(target=serve,args=(path,handle,stopped),kwargs={'idle_timeout':.1})
            thread.start()
            client=None
            try:
                deadline=time.monotonic()+3
                while not path.exists() and time.monotonic()<deadline:time.sleep(.01)
                client=threading.Thread(target=lambda:replies.append(request(path,{})))
                client.start();self.assertTrue(entered.wait(timeout=2))
                time.sleep(.6)
                self.assertTrue(thread.is_alive())
                release.set();client.join(timeout=2);thread.join(timeout=2)
                self.assertEqual(replies,[{'text':'готово'}])
                self.assertFalse(thread.is_alive());self.assertFalse(path.exists())
            finally:
                release.set();stopped.set();thread.join(timeout=4)
                if client:client.join(timeout=4)

    def test_large_response_requires_explicit_bounded_limit(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'voice/control.sock';stopped=threading.Event()
            text='Русская речь. '*1000
            thread=threading.Thread(target=serve,args=(path,lambda body:{'text':text},stopped))
            thread.start()
            try:
                deadline=time.monotonic()+3
                while not path.exists() and time.monotonic()<deadline:time.sleep(.01)
                with self.assertRaises(ValueError):request(path,{})
                self.assertEqual(request(path,{},response_limit=131072),{'text':text})
            finally:stopped.set();thread.join(timeout=4)

    def test_local_request_is_bounded_private_and_has_one_handler_call(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'voice/control.sock';stopped=threading.Event();calls=[]
            def handle(body):calls.append(body);return {'status':'ok'}
            thread=threading.Thread(target=serve,args=(path,handle,stopped));thread.start()
            try:
                deadline=time.monotonic()+3
                while not path.exists() and time.monotonic()<deadline:time.sleep(.01)
                self.assertEqual(path.stat().st_mode&0o777,0o600)
                self.assertEqual(path.parent.stat().st_mode&0o777,0o700)
                self.assertEqual(request(path,{'mode':'dictate'}),{'status':'ok'})
                self.assertEqual(calls,[{'mode':'dictate'}])
            finally:stopped.set();thread.join(timeout=4)
            self.assertFalse(thread.is_alive());self.assertFalse(path.exists())
