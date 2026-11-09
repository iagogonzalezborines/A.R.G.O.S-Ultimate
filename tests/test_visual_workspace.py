"""Security regression: presentation references cannot smuggle controller operations."""
import importlib.util
from pathlib import Path
import unittest
import tempfile
import tomllib
P=Path(__file__).resolve().parents[1]/'experiments/hermes-pilot'
spec=importlib.util.spec_from_file_location('visual_workspace_test',P/'ui-workbench/runtime/visual_workspace.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class VisualWorkspaceTests(unittest.TestCase):
    def test_model_cannot_supply_shell_geometry_or_approval(self):
        for extra in [{'shell':'touch x'},{'x':10},{'approve':True},{'url':'http://localhost'}]:
            with self.assertRaises(ValueError):m.command({'action':'visual','operation':'hide',**extra})
        for operation in ['approve','dispatch','launch','execute']:
            with self.assertRaises(ValueError):m.command({'action':'visual','operation':operation})

    def test_references_are_explicit_and_no_nested_action_injection(self):
        ref={'project':'p_1','task_id':'t_1','path':'part.stl'}
        self.assertEqual(m.command({'action':'visual','operation':'present','ref':ref})['ref'],ref)
        for bad in [{**ref,'action':'confirm'},{**ref,'project':'../credentials'},None]:
            with self.assertRaises(ValueError):m.command({'action':'visual','operation':'present','ref':bad})
        for a in [{'operation':'present'},{'operation':'move','id':'a'*16,'display':'second'},{'operation':'swap','id':'a'*16}]:
            with self.assertRaises(ValueError):m.command({'action':'visual',**a})

    def test_transport_activation_is_narrow_and_preserves_custom_policy(self):
        spec=importlib.util.spec_from_file_location('workspace_installer',P.parents[1]/'scripts/prepare_hermes_pilot.py');installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);file=root/'state/codex/config.toml';file.parent.mkdir(parents=True)
            import json
            source='[mcp_servers.argos-workspace]\ncommand='+json.dumps(str(root/'env/bin/python'))+'\nargs=['+json.dumps(str(root/'checks/workspace_mcp.py'))+']\nenabled_tools=["workspace","files"]\n'
            file.write_text(source);installer.configure_workspace_control(root,True);installer.configure_workspace_control(root,True)
            parsed=tomllib.loads(file.read_text());self.assertEqual(parsed['mcp_servers']['argos-workspace']['tools'],{'workspace':{'approval_mode':'approve'}})
            installer.configure_workspace_control(root,False);self.assertEqual(file.read_text().strip(),source.strip())
            for bad in [source.replace('workspace_mcp.py','other.py'),source+'[mcp_servers.argos-workspace.tools.workspace]\napproval_mode="deny"\n']:
                file.write_text(bad)
                with self.assertRaises(ValueError):installer.configure_workspace_control(root,True)
                self.assertEqual(file.read_text(),bad)

if __name__=='__main__':unittest.main()
