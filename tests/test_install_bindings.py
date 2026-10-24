from __future__ import annotations

import importlib.util
from pathlib import Path
import shlex
import tomllib
import unittest


spec = importlib.util.spec_from_file_location(
    'activate_english', Path(__file__).resolve().parents[1] / 'scripts/activate-english-modes.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class BindingsTest(unittest.TestCase):
    def test_first_install_without_config(self):
        result = tomllib.loads(installer.add_bindings('', Path('/opt/gerda-english')))
        self.assertEqual([c['key'] for c in result['keys']['command']], ['f7', 'f6'])
        self.assertTrue(all(c['type'] == 'shell' for c in result['keys']['command']))

    def test_preserves_russian_key_and_existing_settings(self):
        original = 'onboarding = false\n[[keys.command]]\nkey="f8"\ntype="shell"\ncommand="herdr-dictate"\n'
        result = tomllib.loads(installer.add_bindings(original, Path('/opt/gerda-english')))
        self.assertFalse(result['onboarding'])
        self.assertEqual(result['keys']['command'][0]['command'], 'herdr-dictate')
        self.assertEqual(len(result['keys']['command']), 3)

    def test_repeated_activation_does_not_duplicate_keys(self):
        wrapper = Path('/opt/gerda-english')
        first = installer.add_bindings('', wrapper)
        self.assertEqual(installer.add_bindings(first, wrapper), first)

    def test_conflicts_require_manual_resolution(self):
        for original in [
            '[[keys.command]]\nkey="F7"\ntype="shell"\ncommand="another-command"\n',
            '[[keys.command]]\nkey="f6"\ntype="pane"\ncommand="/opt/gerda-english speak"\n',
        ]:
            with self.subTest(config=original), self.assertRaisesRegex(ValueError, 'already bound'):
                installer.add_bindings(original, Path('/opt/gerda-english'))

    def test_quoted_path_survives_toml_and_shell_parsing(self):
        wrapper = Path('/opt/a "quoted" directory/gerda-english')
        result = tomllib.loads(installer.add_bindings('', wrapper))
        self.assertEqual(shlex.split(result['keys']['command'][0]['command']), [str(wrapper), 'dictate'])
