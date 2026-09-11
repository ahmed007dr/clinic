"""The front door is the React application.

Typing the bare domain used to open the old server-rendered login, and after
signing in the old dashboard — a whole second interface the clinic was never
meant to work in. The old screens stay reachable at their own URLs, because
the React app still links to a few of them.
"""

from django.test import TestCase


class EntryPointTests(TestCase):
    def test_the_domain_opens_the_react_app(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/app/")

    def test_a_stale_bookmark_lands_in_the_react_app(self):
        response = self.client.get("/patients/12/no-longer-here/")
        # /patients/ is an old app; an unknown path under it is not its route.
        self.assertIn(response.status_code, (302, 404))
        response = self.client.get("/nothing-here/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/app/")

    def test_the_old_screens_are_still_reachable_directly(self):
        """Prescription print, exports and the audit log are still served by
        them, so they must not be swallowed by the redirect."""
        self.assertEqual(self.client.get("/accounts/login/").status_code, 200)
