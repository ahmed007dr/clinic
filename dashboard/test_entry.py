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

    def test_the_old_interface_is_gone_and_lands_in_the_react_app(self):
        """The old login, dashboard and list screens no longer exist: their
        addresses — bookmarks, old emails — all end up in the React app."""
        for path in ("/accounts/login/", "/dashboard/", "/patients/", "/appointments/", "/billing/expense/",
                     "/employees/", "/services/", "/branches/", "/notifications/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertEqual(response["Location"], "/app/")

    def test_what_react_links_to_is_still_served(self):
        """Prints and exports live at their own addresses, and must not be
        swallowed by the redirect above (a signed-out visitor is sent to the
        React sign-in instead)."""
        for path in ("/patients/print/intake/", "/patients/export/", "/billing/export/", "/audit/"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 302)
                self.assertTrue(response["Location"].startswith("/app/login"), response["Location"])

    def test_an_unknown_api_address_is_a_404_not_a_redirect_to_an_html_page(self):
        """A redirect would make a mistyped endpoint look like a hang."""
        response = self.client.get("/api/nothing-here/")
        self.assertEqual(response.status_code, 404)
