from django.test import TestCase
from django.urls import reverse

from apps.catalog.models import Category, Product, ProductStatus


class TestBasicViews(TestCase):
    def test_landing_page(self):
        self._assert_200(reverse("web:home"))

    def test_signup(self):
        self._assert_200(reverse("account_signup"))

    def test_login(self):
        self._assert_200(reverse("account_login"))

    def test_terms(self):
        self._assert_200(reverse("web:terms"))

    def test_robots(self):
        self._assert_200(reverse("web:robots.txt"))

    def _assert_200(self, url):
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class TestSearchViews(TestCase):
    def test_perfume_search_matches_fragrance_products(self):
        category = Category.objects.create(name="Fragrances", slug="fragrances")
        Product.objects.create(
            name="Dior J'adore",
            slug="dior-j-adore",
            category=category,
            status=ProductStatus.ACTIVE,
            description="A luxurious floral fragrance.",
        )

        response = self.client.get(reverse("web:search_results"), {"q": "perfume"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dior J&#x27;adore", html=False)
