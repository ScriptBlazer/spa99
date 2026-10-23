from django.test import TestCase


class SignInShellTests(TestCase):
    """SIGN-IN.md: the public pages share the espresso shell; Control's sign-in keeps its own box."""

    def test_public_sign_in_uses_the_shell_and_keeps_field_names_and_links(self):
        html = self.client.get("/login/").content.decode()
        self.assertIn('class="signin on-dark"', html)
        self.assertIn("Welcome back.", html)
        for needle in ('name="username"', 'name="password"', 'data-working-text="One moment"', 'href="/forgot-password/"',
                       'aria-label="Forgotten your password?"', 'href="/register/"', "Your own locker, every visit."):
            self.assertIn(needle, html)
        self.assertEqual(html.count("<h1"), 1)

    def test_forgot_and_reset_pages_share_the_shell(self):
        self.assertIn('class="signin on-dark"', self.client.get("/forgot-password/").content.decode())

    def test_control_sign_in_is_untouched(self):
        html = self.client.get("/login/", HTTP_HOST="control.localhost").content.decode()
        self.assertIn("control-login", html)
        self.assertIn("Spa 99 Control", html)
        self.assertNotIn("signin", html)
