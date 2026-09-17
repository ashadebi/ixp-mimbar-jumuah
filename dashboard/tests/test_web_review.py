"""Public registration must enter review, never routing activation."""
import json
from test_onboarding import OnboardingTests
import server as app
import onboarding as ob

class WebReviewTests(OnboardingTests):
    def web(self, **changes):
        payload=dict(asn=13335, organization='Web Network', email='noc@example.org',
                     location='AG', peering_ipv4='103.19.76.250', peering_ipv6='',
                     ipv4_prefixes='1.1.1.0/24', ipv6_prefixes='2606:4700::/32',
                     bandwidth='10G', domain='example.org', as_sets='AS-CLOUDFLARE', contact='Web NOC')
        payload.update(changes)
        return app.create_member_application(payload)

    def test_web_submission_enters_pending_review(self):
        loc=app.get_location('AG')
        result=self.web()
        row=app.query('SELECT * FROM member_requests WHERE id=?',(result['id'],),True)
        self.assertIsNotNone(row, 'public submission missing from admin review')
        self.assertEqual(row['origin'],'web')
        self.assertIsNone(row['chat_id'])
        self.assertEqual(row['status'],'pending')
        data=json.loads(row['data'])
        self.assertEqual(data['prefix4'],['1.1.1.0/24'])
        self.assertEqual(data['prefix6'],['2606:4700::/32'])
        self.assertEqual(data['as_sets'],['AS-CLOUDFLARE'])
        self.assertEqual(data['peering4'],'103.19.76.250')
        self.assertEqual(data['contact'],'Web NOC')
        self.assertEqual(data['email'],'noc@example.org')
        self.assertEqual(app.get_location('AG')['clients'],loc['clients'])
        self.assertEqual(app.get_location('AG')['revision'],loc['revision'])
        self.assertFalse(app.query('SELECT * FROM jobs'))
        self.assertEqual(ob.listing(app.connect)['requests'][0]['id'],result['id'])
        old=app.query('SELECT * FROM member_applications WHERE id=?',(result['id'],),True)
        self.assertEqual(old['pairing_code'],result['pairing_code'])
        self.assertTrue(old['telegram_code'])
        self.web(email='other@example.org')
        self.assertEqual(len(ob.listing(app.connect)['requests']),2)
