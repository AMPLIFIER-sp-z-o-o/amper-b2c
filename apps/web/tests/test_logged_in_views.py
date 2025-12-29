from django.urls import reverse

from .base import TestLoginRequiredViewBase


class TestProfileViews(TestLoginRequiredViewBase):
    def test_profile(self):
        self._run_tests(reverse("users:user_profile"))

    def test_password_change(self):
        self._run_tests(reverse("account_change_password"))

    def test_2fa_setup(self):
        self._run_tests(reverse("mfa_index"))
