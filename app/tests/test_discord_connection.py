import unittest
from speaker_labels import validate_widget_url, widget_connection_status


class DiscordConnectionTests(unittest.TestCase):
    def test_regular_channel_link_is_converted_without_extra_permissions(self):
        self.assertEqual(validate_widget_url('https://discord.com/channels/123456789012345678/234567890123456789'),
                         'https://streamkit.discord.com/overlay/voice/123456789012345678/234567890123456789')

    def test_channel_link_query_is_not_forwarded(self):
        self.assertNotIn('?',validate_widget_url('https://discord.com/channels/123456789012345678/234567890123456789?test=1'))

    def test_other_link_types_are_rejected(self):
        for url in ['https://discord.com/channels/@me/234567890123456789',
                    'https://discord.gg/example',
                    'https://discord.com.evil.test/channels/123456789012345678/234567890123456789',
                    'https://user@discord.com/channels/123456789012345678/234567890123456789',
                    'http://discord.com/channels/123456789012345678/234567890123456789',
                    'https://discord.com:bad/channels/123456789012345678/234567890123456789']:
            with self.assertRaises(ValueError):validate_widget_url(url)

    def test_open_socket_does_not_mean_authorized(self):
        ready,text=widget_connection_status({'connected':True,'rpc':{'authorized':False}})
        self.assertFalse(ready)
        self.assertIn('아직',text)

    def test_authorization_alone_does_not_mean_channel_ready(self):
        ready,text=widget_connection_status({'connected':True,'rpc':{'authorized':True,'channel':False}})
        self.assertFalse(ready)
        self.assertIn('불러오는 중',text)

    def test_authorization_error_is_actionable(self):
        ready,text=widget_connection_status({'connected':True,'rpc':{'error':'AUTHORIZE','code':4006}})
        self.assertFalse(ready)
        self.assertIn('승인 실패',text)
        self.assertIn('4006',text)

    def test_channel_error_does_not_claim_connected(self):
        ready,text=widget_connection_status({'connected':True,'rpc':{'authorized':True,'error':'GET_CHANNEL','code':4006}})
        self.assertFalse(ready)
        self.assertIn('통화방 정보를 읽지 못했습니다',text)

    def test_only_confirmed_channel_can_attribute_names(self):
        state={'connected':True,'rpc':{'authorized':True,'channel':True}}
        self.assertTrue(widget_connection_status(state)[0])
        self.assertFalse(widget_connection_status(state,setup=True)[0])
