import unittest
from unittest.mock import AsyncMock, patch
from argos.media import control, status
from argos.models import ArgosError

class MediaTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.proc=patch('argos.media.process',AsyncMock());self.process=self.proc.start()
        self.which=patch('argos.media.shutil.which',return_value='/usr/bin/playerctl');self.which.start()
        self.args={'player':'firefox','action':'play','expected_title':'AC/DC - Thunderstruck'}
    async def asyncTearDown(self):
        self.proc.stop();self.which.stop()
    def replies(self,*values):
        self.process.side_effect=[(0,v,'') for v in values]
    async def test_verifies_specific_player_and_loaded_title(self):
        self.replies('firefox.instance_1\n','Paused\nAC/DC - Thunderstruck\n','','Playing\nAC/DC - Thunderstruck\n')
        r=await control(None,self.args)
        self.assertEqual(r['verification'],'media_state_observed')
        self.assertEqual(self.process.call_args_list[2].args[0],['playerctl','--player=firefox.instance_1','play'])
    async def test_wrong_title_never_plays(self):
        self.replies('firefox.instance_1\n','Paused\nUnrelated video\n')
        with self.assertRaises(ArgosError): await control(None,self.args)
        self.assertEqual(self.process.await_count,2)
    async def test_ambiguous_player_never_plays(self):
        self.replies('firefox.instance_1\nfirefox.instance_2\n')
        with self.assertRaises(ArgosError): await control(None,self.args)
        self.assertEqual(self.process.await_count,1)
    async def test_no_toggle_if_already_playing(self):
        self.replies('firefox.instance_1\n','Playing\nAC/DC - Thunderstruck\n','Playing\nAC/DC - Thunderstruck\n')
        await control(None,self.args)
        self.assertTrue(all('play' not in c.args[0] for c in self.process.call_args_list))
    async def test_track_change_after_command_does_not_claim_success(self):
        self.replies('firefox.instance_1\n','Paused\nAC/DC - Thunderstruck\n','','Playing\nAnother video\n')
        with self.assertRaises(ArgosError): await control(None,self.args)
    async def test_rejected_action_never_touches_player(self):
        with self.assertRaises(ArgosError): await control(None,{**self.args,'action':'open'})
        self.process.assert_not_called()
    async def test_status_only_reads_metadata(self):
        self.replies('firefox.instance_1\n','Playing\nA video\n')
        r=await status(None,{})
        self.assertEqual(r['evidence']['players'][0]['title'],'A video')
