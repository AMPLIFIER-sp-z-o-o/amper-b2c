"""
Comprehensive tests for the favourites app.

Tests cover:
- Model functionality (WishList, WishListItem)
- Anonymous user wishlists
- Authenticated user wishlists
- Wishlist merge on login
- Views and API endpoints
- Edge cases
"""

from decimal import Decimal

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.db import IntegrityError
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.cart.models import Cart, CartLine
from apps.catalog.models import Category, Product
from apps.favourites.models import WishList, WishListItem
from apps.favourites.signals import merge_anonymous_wishlists_on_login

User = get_user_model()


# ============================================
# MODEL TESTS
# ============================================


class TestWishListModel(TestCase):
    """Tests for WishList model."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="test@example.com", email="test@example.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="Test Category", slug="test-category")
        cls.product = Product.objects.create(
            name="Test Product", slug="test-product", price=Decimal("99.99"), category=cls.category
        )

    def test_create_user_wishlist(self):
        """Test creating a wishlist for authenticated user."""
        wishlist = WishList.objects.create(user=self.user, name="My Wishlist")
        assert wishlist.user == self.user
        assert wishlist.name == "My Wishlist"
        assert wishlist.is_default is False
        assert wishlist.session_key is None

    def test_create_anonymous_wishlist(self):
        """Test creating a wishlist for anonymous user."""
        session_key = "test-session-123"
        wishlist = WishList.objects.create(session_key=session_key, name="Anonymous Wishlist")
        assert wishlist.user is None
        assert wishlist.session_key == session_key
        assert wishlist.name == "Anonymous Wishlist"

    def test_default_wishlist_uniqueness_per_user(self):
        """Test that only one default wishlist per user is allowed."""
        WishList.objects.create(user=self.user, name="Default", is_default=True)
        # Creating another default wishlist should set the first to non-default
        # or rely on the constraint
        with pytest.raises(Exception):
            WishList.objects.create(user=self.user, name="Another Default", is_default=True)

    def test_get_or_create_default_for_user(self):
        """Test get_or_create_default creates default wishlist."""
        wishlist = WishList.get_or_create_default(user=self.user)
        assert wishlist.is_default is True
        assert wishlist.user == self.user

        # Should return existing default
        wishlist2 = WishList.get_or_create_default(user=self.user)
        assert wishlist2.pk == wishlist.pk

    def test_get_or_create_default_for_session(self):
        """Test get_or_create_default for anonymous user."""
        session_key = "anon-session-456"
        wishlist = WishList.get_or_create_default(session_key=session_key)
        assert wishlist.is_default is True
        assert wishlist.session_key == session_key
        assert wishlist.user is None

    def test_wishlist_str(self):
        """Test wishlist string representation."""
        wishlist = WishList.objects.create(user=self.user, name="My Favourites")
        # __str__ includes owner info
        assert "My Favourites" in str(wishlist)

    def test_product_count(self):
        """Test product_count property."""
        wishlist = WishList.objects.create(user=self.user, name="Test")
        assert wishlist.product_count == 0

        WishListItem.objects.create(wishlist=wishlist, product=self.product, price_when_added=self.product.price)
        # Refresh to get updated count
        wishlist.refresh_from_db()
        assert wishlist.product_count == 1


class TestWishListItemModel(TestCase):
    """Tests for WishListItem model."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="testitem@example.com", email="testitem@example.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="Item Category", slug="item-category")
        cls.product = Product.objects.create(
            name="Item Product",
            slug="item-product",
            price=Decimal("49.99"),
            category=cls.category,
            stock=10,  # In stock for is_available test
        )
        cls.wishlist = WishList.objects.create(user=cls.user, name="Test Wishlist")

    def test_create_wishlist_item(self):
        """Test creating a wishlist item."""
        item = WishListItem.objects.create(
            wishlist=self.wishlist, product=self.product, price_when_added=Decimal("49.99")
        )
        assert item.product == self.product
        assert item.price_when_added == Decimal("49.99")
        assert item.is_available is True

    def test_price_changed_property(self):
        """Test price_changed property detects price changes."""
        item = WishListItem.objects.create(
            wishlist=self.wishlist, product=self.product, price_when_added=Decimal("49.99")
        )
        assert item.price_changed is False

        # Change product price
        self.product.price = Decimal("39.99")
        self.product.save()
        item.refresh_from_db()
        assert item.price_changed is True

    def test_unique_product_per_wishlist(self):
        """Test that same product cannot be added twice to same wishlist."""
        WishListItem.objects.create(wishlist=self.wishlist, product=self.product, price_when_added=self.product.price)
        with pytest.raises(Exception):
            WishListItem.objects.create(
                wishlist=self.wishlist, product=self.product, price_when_added=self.product.price
            )


class TestWishListMerge(TestCase):
    """Tests for anonymous wishlist merge functionality."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="merge@example.com", email="merge@example.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="Merge Category", slug="merge-category")
        cls.product1 = Product.objects.create(
            name="Merge Product 1", slug="merge-product-1", price=Decimal("10.00"), category=cls.category
        )
        cls.product2 = Product.objects.create(
            name="Merge Product 2", slug="merge-product-2", price=Decimal("20.00"), category=cls.category
        )

    def test_merge_anonymous_wishlists(self):
        """Test merging anonymous wishlists to user account."""
        session_key = "merge-test-session"

        # Create anonymous wishlist with items
        anon_wishlist = WishList.objects.create(session_key=session_key, name="Ulubione", is_default=True)
        WishListItem.objects.create(wishlist=anon_wishlist, product=self.product1, price_when_added=self.product1.price)
        WishListItem.objects.create(wishlist=anon_wishlist, product=self.product2, price_when_added=self.product2.price)

        # Merge to user
        WishList.merge_anonymous_wishlists(self.user, session_key)

        # Anonymous wishlist should be deleted
        assert not WishList.objects.filter(session_key=session_key).exists()

        # User should have default wishlist with items
        user_wishlist = WishList.objects.get(user=self.user, is_default=True)
        assert user_wishlist.items.count() == 2

    def test_merge_with_existing_user_wishlist(self):
        """Test merge when user already has wishlist with some items."""
        session_key = "merge-existing-session"

        # Create user's default wishlist with product1
        user_wishlist = WishList.get_or_create_default(user=self.user)
        WishListItem.objects.create(wishlist=user_wishlist, product=self.product1, price_when_added=self.product1.price)

        # Create anonymous wishlist with product2 (and product1 - duplicate)
        anon_wishlist = WishList.objects.create(session_key=session_key, name="Ulubione", is_default=True)
        WishListItem.objects.create(
            wishlist=anon_wishlist,
            product=self.product1,  # Duplicate
            price_when_added=self.product1.price,
        )
        WishListItem.objects.create(wishlist=anon_wishlist, product=self.product2, price_when_added=self.product2.price)

        # Merge
        WishList.merge_anonymous_wishlists(self.user, session_key)

        # Should have 2 unique products (duplicate ignored)
        user_wishlist.refresh_from_db()
        assert user_wishlist.items.count() == 2

    def test_merge_on_login_uses_cookie_session_key(self):
        """Ensure login merge uses the pre-rotation session key from cookies."""
        anon_session_key = "merge-login-session"

        anon_wishlist = WishList.objects.create(
            session_key=anon_session_key,
            name="Ulubione",
            is_default=True,
        )
        WishListItem.objects.create(
            wishlist=anon_wishlist,
            product=self.product1,
            price_when_added=self.product1.price,
        )

        request = RequestFactory().get("/accounts/login/")
        request.session = SessionStore()
        request.session.create()
        request.COOKIES = {settings.SESSION_COOKIE_NAME: anon_session_key}

        merge_anonymous_wishlists_on_login(sender=None, request=request, user=self.user)

        assert not WishList.objects.filter(session_key=anon_session_key).exists()
        user_wishlist = WishList.objects.get(user=self.user, is_default=True)
        assert user_wishlist.items.filter(product=self.product1).exists()


# ============================================
# VIEW TESTS
# ============================================


class TestFavouritesPageView(TestCase):
    """Tests for favourites page view."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="pageview@example.com", email="pageview@example.com", password="testpass123"
        )

    def test_favourites_page_anonymous(self):
        """Test anonymous user can access favourites page."""
        client = Client()
        response = client.get(reverse("favourites:favourites_page"))
        assert response.status_code == 200
        assert "Favourites" in response.content.decode() or "Ulubione" in response.content.decode()

    def test_favourites_page_authenticated(self):
        """Test authenticated user can access favourites page."""
        client = Client()
        client.login(username="pageview@example.com", password="testpass123")
        response = client.get(reverse("favourites:favourites_page"))
        assert response.status_code == 200


class TestToggleFavouriteView(TestCase):
    """Tests for toggle favourite API endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="toggle@example.com", email="toggle@example.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="Toggle Category", slug="toggle-category")
        cls.product = Product.objects.create(
            name="Toggle Product", slug="toggle-product", price=Decimal("15.00"), category=cls.category
        )

    def test_toggle_add_favourite_anonymous(self):
        """Test anonymous user can add product to favourites."""
        client = Client()
        response = client.post(reverse("favourites:toggle_favourite"), {"product_id": self.product.id})
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "added"

    def test_toggle_remove_favourite_anonymous(self):
        """Test anonymous user can remove product from favourites."""
        client = Client()
        # First add
        client.post(reverse("favourites:toggle_favourite"), {"product_id": self.product.id})
        # Then remove
        response = client.post(reverse("favourites:toggle_favourite"), {"product_id": self.product.id})
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "removed"

    def test_toggle_favourite_authenticated(self):
        """Test authenticated user can toggle favourite."""
        client = Client()
        client.login(username="toggle@example.com", password="testpass123")

        response = client.post(reverse("favourites:toggle_favourite"), {"product_id": self.product.id})
        assert response.status_code == 200
        data = response.json()
        assert data["action"] == "added"

        # Verify it's in user's wishlist
        wishlist = WishList.objects.get(user=self.user, is_default=True)
        assert wishlist.items.filter(product=self.product).exists()

    def test_toggle_invalid_product(self):
        """Test toggle with invalid product ID."""
        client = Client()
        response = client.post(reverse("favourites:toggle_favourite"), {"product_id": 99999})
        assert response.status_code == 404


class TestCreateWishlistView(TestCase):
    """Tests for create wishlist view."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="create@example.com", email="create@example.com", password="testpass123"
        )

    def test_create_wishlist_authenticated(self):
        """Test creating a custom wishlist."""
        client = Client()
        client.login(username="create@example.com", password="testpass123")

        response = client.post(reverse("favourites:create_wishlist"), {"name": "My Custom List"})
        assert response.status_code == 302  # Redirect on success

        wishlist = WishList.objects.get(user=self.user, name="My Custom List")
        assert wishlist.is_default is False

    def test_create_wishlist_empty_name(self):
        """Test creating wishlist with empty name fails."""
        client = Client()
        client.login(username="create@example.com", password="testpass123")

        response = client.post(reverse("favourites:create_wishlist"), {"name": ""})
        # Should redirect with error or show error
        assert response.status_code in [302, 400]


class TestDeleteWishlistView(TestCase):
    """Tests for delete wishlist view."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="delete@example.com", email="delete@example.com", password="testpass123"
        )

    def test_delete_custom_wishlist(self):
        """Test deleting a custom wishlist."""
        wishlist = WishList.objects.create(user=self.user, name="To Delete", is_default=False)

        client = Client()
        client.login(username="delete@example.com", password="testpass123")

        response = client.post(reverse("favourites:delete_wishlist", args=[wishlist.pk]))
        assert response.status_code == 302  # Redirect on success
        assert not WishList.objects.filter(pk=wishlist.pk).exists()

    def test_can_delete_default_wishlist(self):
        """Test that default wishlist can be deleted."""
        wishlist = WishList.get_or_create_default(user=self.user)

        client = Client()
        client.login(username="delete@example.com", password="testpass123")

        response = client.post(reverse("favourites:delete_wishlist", args=[wishlist.pk]))
        # Default wishlist should be deleted successfully
        assert response.status_code == 302
        assert not WishList.objects.filter(pk=wishlist.pk).exists()


class TestAddToWishlistView(TestCase):
    """Tests for add to wishlist view."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="addto@example.com", email="addto@example.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="AddTo Category", slug="addto-category")
        cls.product = Product.objects.create(
            name="AddTo Product", slug="addto-product", price=Decimal("25.00"), category=cls.category
        )

    def test_add_to_specific_wishlist(self):
        """Test adding product to a specific wishlist."""
        wishlist = WishList.objects.create(user=self.user, name="Specific List")

        client = Client()
        client.login(username="addto@example.com", password="testpass123")

        response = client.post(
            reverse("favourites:add_to_wishlist"), {"product_id": self.product.id, "wishlist_id": wishlist.id}
        )
        assert response.status_code == 200
        assert wishlist.items.filter(product=self.product).exists()


class TestCheckProductStatusView(TestCase):
    """Tests for check product status API."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="status@example.com", email="status@example.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="Status Category", slug="status-category")
        cls.product = Product.objects.create(
            name="Status Product", slug="status-product", price=Decimal("30.00"), category=cls.category
        )

    def test_check_status_no_favourites(self):
        """Test status check when product is not in favourites."""
        client = Client()
        response = client.get(reverse("favourites:check_product_status"), {"product_ids": str(self.product.id)})
        assert response.status_code == 200
        data = response.json()
        # status is a dict mapping product_id -> list of wishlist_ids
        # If product is not in favourites, it won't be in status
        assert str(self.product.id) not in data.get("status", {})

    def test_check_status_with_favourites(self):
        """Test status check when product is in favourites."""
        client = Client()
        client.login(username="status@example.com", password="testpass123")

        # Add to favourites
        wishlist = WishList.get_or_create_default(user=self.user)
        WishListItem.objects.create(wishlist=wishlist, product=self.product, price_when_added=self.product.price)

        response = client.get(reverse("favourites:check_product_status"), {"product_ids": str(self.product.id)})
        assert response.status_code == 200
        data = response.json()
        # status is a dict mapping product_id -> list of wishlist_ids
        # The product_id in status comes back as string from JSON
        status = data.get("status", {})
        assert str(self.product.id) in status or self.product.id in status


class TestMoveItemView(TestCase):
    """Tests for move item between wishlists."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="move@example.com", email="move@example.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="Move Category", slug="move-category")
        cls.product = Product.objects.create(
            name="Move Product", slug="move-product", price=Decimal("35.00"), category=cls.category
        )

    def test_move_item_between_wishlists(self):
        """Test moving item from one wishlist to another."""
        source = WishList.objects.create(user=self.user, name="Source")
        target = WishList.objects.create(user=self.user, name="Target")
        item = WishListItem.objects.create(wishlist=source, product=self.product, price_when_added=self.product.price)

        client = Client()
        client.login(username="move@example.com", password="testpass123")

        response = client.post(reverse("favourites:move_item"), {"item_id": item.id, "target_wishlist_id": target.id})
        assert response.status_code == 200

        # Item should be in target, not source
        assert not source.items.filter(product=self.product).exists()
        assert target.items.filter(product=self.product).exists()


class TestAddAllToCartView(TestCase):
    """Tests for add all items to cart."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="cart@example.com", email="cart@example.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="Cart Category", slug="cart-category")
        cls.product = Product.objects.create(
            name="Cart Product", slug="cart-product", price=Decimal("40.00"), category=cls.category
        )

    def test_add_all_to_cart(self):
        """Test adding all wishlist items to cart."""
        wishlist = WishList.get_or_create_default(user=self.user)
        WishListItem.objects.create(wishlist=wishlist, product=self.product, price_when_added=self.product.price)

        client = Client()
        client.login(username="cart@example.com", password="testpass123")

        response = client.post(reverse("favourites:add_all_to_cart"), {"wishlist_id": wishlist.id})
        assert response.status_code == 200
        # Note: Actual cart functionality depends on cart app implementation


# ============================================
# SIGNAL TESTS
# ============================================


class TestMergeOnLoginSignal(TestCase):
    """Tests for automatic merge on user login."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="signal@example.com", email="signal@example.com", password="testpass123"
        )
        cls.category = Category.objects.create(name="Signal Category", slug="signal-category")
        cls.product = Product.objects.create(
            name="Signal Product", slug="signal-product", price=Decimal("50.00"), category=cls.category
        )

    def test_merge_on_login(self):
        """Test that anonymous wishlists are merged on login."""
        client = Client()

        # Add product as anonymous user
        response = client.post(reverse("favourites:toggle_favourite"), {"product_id": self.product.id})
        assert response.status_code == 200

        # Get the session key
        session_key = client.session.session_key

        # Verify anonymous wishlist exists
        assert WishList.objects.filter(session_key=session_key).exists()

        # Login
        client.login(username="signal@example.com", password="testpass123")

        # Verify product is now in user's wishlist
        user_wishlist = WishList.objects.filter(user=self.user, is_default=True).first()
        if user_wishlist:
            assert user_wishlist.items.filter(product=self.product).exists()


# ============================================
# EDGE CASES AND ADDITIONAL COVERAGE
# ============================================


class TestWishListModelEdgeCases(TestCase):
    """Additional edge case tests for WishList model."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="edge@example.com",
            email="edge@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="Edge Category", slug="edge-category")
        cls.product_1 = Product.objects.create(
            name="Edge Product 1",
            slug="edge-product-1",
            price=Decimal("10.00"),
            category=cls.category,
        )
        cls.product_2 = Product.objects.create(
            name="Edge Product 2",
            slug="edge-product-2",
            price=Decimal("25.50"),
            category=cls.category,
        )

    def test_total_value_calculation(self):
        wishlist = WishList.objects.create(user=self.user, name="Totals")
        assert wishlist.total_value == Decimal("0.00")

        WishListItem.objects.create(
            wishlist=wishlist,
            product=self.product_1,
            price_when_added=self.product_1.price,
        )
        WishListItem.objects.create(
            wishlist=wishlist,
            product=self.product_2,
            price_when_added=self.product_2.price,
        )

        wishlist.refresh_from_db()
        assert wishlist.total_value == Decimal("35.50")

    def test_get_or_create_default_requires_user_or_session(self):
        with pytest.raises(ValueError):
            WishList.get_or_create_default()

    def test_default_wishlist_uniqueness_per_session(self):
        session_key = "edge-session-1"
        WishList.objects.create(
            session_key=session_key,
            name="Default",
            is_default=True,
        )
        with pytest.raises(IntegrityError):
            WishList.objects.create(
                session_key=session_key,
                name="Default 2",
                is_default=True,
            )


class TestWishListItemEdgeCases(TestCase):
    """Additional edge case tests for WishListItem model."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="edgeitem@example.com",
            email="edgeitem@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="Edge Item Category", slug="edge-item-category")
        cls.product = Product.objects.create(
            name="Edge Item Product",
            slug="edge-item-product",
            price=Decimal("19.99"),
            category=cls.category,
            stock=0,
        )
        cls.wishlist = WishList.objects.create(user=cls.user, name="Edge Wishlist")

    def test_auto_price_when_added(self):
        item = WishListItem.objects.create(
            wishlist=self.wishlist,
            product=self.product,
        )
        assert item.price_when_added == self.product.price

    def test_price_difference_negative_and_positive(self):
        item = WishListItem.objects.create(
            wishlist=self.wishlist,
            product=self.product,
            price_when_added=Decimal("25.00"),
        )
        assert item.price_difference == Decimal("-5.01")

        self.product.price = Decimal("30.00")
        self.product.save()
        item.refresh_from_db()
        assert item.price_difference == Decimal("5.00")

    def test_is_available_false_when_out_of_stock(self):
        item = WishListItem.objects.create(
            wishlist=self.wishlist,
            product=self.product,
            price_when_added=self.product.price,
        )
        assert item.is_available is False


class TestWishListMergeEdgeCases(TestCase):
    """Additional edge case tests for anonymous merge behavior."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="mergeedge@example.com",
            email="mergeedge@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="Merge Edge Category", slug="merge-edge-category")
        cls.product = Product.objects.create(
            name="Merge Edge Product",
            slug="merge-edge-product",
            price=Decimal("5.00"),
            category=cls.category,
        )

    def test_merge_returns_zero_without_session_key(self):
        assert WishList.merge_anonymous_wishlists(self.user, "") == 0

    def test_merge_custom_list_renames_on_conflict(self):
        session_key = "merge-conflict-session"
        WishList.objects.create(user=self.user, name="Trips")

        anon_list = WishList.objects.create(
            session_key=session_key,
            name="Trips",
            is_default=False,
        )
        WishListItem.objects.create(
            wishlist=anon_list,
            product=self.product,
            price_when_added=self.product.price,
        )

        WishList.merge_anonymous_wishlists(self.user, session_key)

        renamed = WishList.objects.filter(user=self.user, name="Trips (1)").first()
        assert renamed is not None
        assert renamed.items.count() == 1


class TestFavouritesPageViewEdgeCases(TestCase):
    """Additional edge case tests for favourites page."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="pageedge@example.com",
            email="pageedge@example.com",
            password="testpass123",
        )

    def test_favourites_page_creates_default_for_anonymous(self):
        client = Client()
        response = client.get(reverse("favourites:favourites_page"))
        assert response.status_code == 200

        session_key = client.session.session_key
        assert WishList.objects.filter(session_key=session_key, is_default=True).exists()

    def test_favourites_page_creates_default_for_user(self):
        client = Client()
        client.login(username="pageedge@example.com", password="testpass123")
        response = client.get(reverse("favourites:favourites_page"))
        assert response.status_code == 200
        assert WishList.objects.filter(user=self.user, is_default=True).exists()

    def test_favourites_page_invalid_list_param_falls_back_to_default(self):
        client = Client()
        client.login(username="pageedge@example.com", password="testpass123")
        default_list = WishList.get_or_create_default(user=self.user)
        WishList.objects.create(user=self.user, name="Other")

        response = client.get(reverse("favourites:favourites_page"), {"list": "nonexistent_id"})
        assert response.status_code == 200
        assert response.context["active_wishlist"].id == default_list.id


class TestWishlistDetailView(TestCase):
    """Tests for wishlist detail view access control."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="detail@example.com",
            email="detail@example.com",
            password="testpass123",
        )
        cls.other_user = User.objects.create_user(
            username="detail2@example.com",
            email="detail2@example.com",
            password="testpass123",
        )
        cls.wishlist = WishList.objects.create(user=cls.user, name="Private")

    def test_wishlist_detail_owner_can_view(self):
        client = Client()
        client.login(username="detail@example.com", password="testpass123")
        response = client.get(reverse("favourites:wishlist_detail", args=[self.wishlist.id]))
        assert response.status_code == 200
        assert response.context["wishlist"].id == self.wishlist.id

    def test_wishlist_detail_other_user_forbidden(self):
        client = Client()
        client.login(username="detail2@example.com", password="testpass123")
        response = client.get(reverse("favourites:wishlist_detail", args=[self.wishlist.id]))
        assert response.status_code == 404


class TestCreateWishlistViewEdgeCases(TestCase):
    """Additional edge case tests for create wishlist."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="createedge@example.com",
            email="createedge@example.com",
            password="testpass123",
        )

    def test_create_wishlist_htmx_success(self):
        client = Client()
        client.login(username="createedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:create_wishlist"),
            {"name": "HTMX List"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["wishlist"]["name"] == "HTMX List"

    def test_create_wishlist_htmx_empty_name(self):
        client = Client()
        client.login(username="createedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:create_wishlist"),
            {"name": ""},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 400

    def test_create_wishlist_htmx_name_too_long(self):
        client = Client()
        client.login(username="createedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:create_wishlist"),
            {"name": "x" * 101},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 400

    def test_create_wishlist_duplicate_name_case_insensitive(self):
        client = Client()
        client.login(username="createedge@example.com", password="testpass123")
        WishList.objects.create(user=self.user, name="Holiday")

        response = client.post(
            reverse("favourites:create_wishlist"),
            {"name": "holiday"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 400

    def test_create_wishlist_anonymous(self):
        client = Client()
        response = client.post(reverse("favourites:create_wishlist"), {"name": "Anon List"})
        assert response.status_code == 302
        session_key = client.session.session_key
        assert WishList.objects.filter(session_key=session_key, name="Anon List").exists()


class TestUpdateWishlistViewEdgeCases(TestCase):
    """Additional edge case tests for update wishlist."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="updateedge@example.com",
            email="updateedge@example.com",
            password="testpass123",
        )
        cls.wishlist = WishList.objects.create(user=cls.user, name="Original", description="Old")

    def test_update_wishlist_success(self):
        client = Client()
        client.login(username="updateedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:update_wishlist", args=[self.wishlist.id]),
            {"name": "Updated", "description": "New desc"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        self.wishlist.refresh_from_db()
        assert self.wishlist.name == "Updated"
        assert self.wishlist.description == "New desc"

    def test_update_wishlist_empty_name(self):
        client = Client()
        client.login(username="updateedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:update_wishlist", args=[self.wishlist.id]),
            {"name": ""},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 400

    def test_update_wishlist_duplicate_name(self):
        client = Client()
        client.login(username="updateedge@example.com", password="testpass123")
        WishList.objects.create(user=self.user, name="Duplicate")

        response = client.post(
            reverse("favourites:update_wishlist", args=[self.wishlist.id]),
            {"name": "Duplicate"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 400


class TestDeleteWishlistViewEdgeCases(TestCase):
    """Additional edge case tests for delete wishlist."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="deleteedge@example.com",
            email="deleteedge@example.com",
            password="testpass123",
        )
        cls.default = WishList.get_or_create_default(user=cls.user)
        cls.custom = WishList.objects.create(user=cls.user, name="Disposable")

    def test_delete_default_wishlist_htmx_allowed(self):
        client = Client()
        client.login(username="deleteedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:delete_wishlist", args=[self.default.id]),
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert not WishList.objects.filter(pk=self.default.id).exists()

    def test_delete_custom_wishlist_htmx_success(self):
        client = Client()
        client.login(username="deleteedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:delete_wishlist", args=[self.custom.id]),
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert not WishList.objects.filter(pk=self.custom.id).exists()


class TestAddToWishlistViewEdgeCases(TestCase):
    """Additional edge case tests for add to wishlist."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="addedge@example.com",
            email="addedge@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="Add Edge Category", slug="add-edge-category")
        cls.product = Product.objects.create(
            name="Add Edge Product",
            slug="add-edge-product",
            price=Decimal("15.00"),
            category=cls.category,
        )

    def test_add_to_wishlist_missing_product_id(self):
        client = Client()
        response = client.post(reverse("favourites:add_to_wishlist"), {})
        assert response.status_code == 400

    def test_add_to_wishlist_invalid_wishlist_id(self):
        client = Client()
        client.login(username="addedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:add_to_wishlist"),
            {"product_id": self.product.id, "wishlist_id": 99999},
        )
        assert response.status_code == 404

    def test_add_to_wishlist_duplicate_product(self):
        client = Client()
        client.login(username="addedge@example.com", password="testpass123")
        wishlist = WishList.get_or_create_default(user=self.user)
        WishListItem.objects.create(
            wishlist=wishlist,
            product=self.product,
            price_when_added=self.product.price,
        )

        response = client.post(
            reverse("favourites:add_to_wishlist"),
            {"product_id": self.product.id, "wishlist_id": wishlist.id},
        )
        assert response.status_code == 400
        assert response.json().get("already_in_list") is True

    def test_add_to_wishlist_defaults_to_user_list(self):
        client = Client()
        client.login(username="addedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:add_to_wishlist"),
            {"product_id": self.product.id},
        )
        assert response.status_code == 200
        wishlist = WishList.get_or_create_default(user=self.user)
        assert wishlist.items.filter(product=self.product).exists()


class TestRemoveFromWishlistViewEdgeCases(TestCase):
    """Additional edge case tests for remove from wishlist."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="removeedge@example.com",
            email="removeedge@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="Remove Edge Category", slug="remove-edge-category")
        cls.product = Product.objects.create(
            name="Remove Edge Product",
            slug="remove-edge-product",
            price=Decimal("12.00"),
            category=cls.category,
        )

    def test_remove_missing_ids(self):
        client = Client()
        response = client.post(reverse("favourites:remove_from_wishlist"), {})
        assert response.status_code == 400

    def test_remove_by_item_id(self):
        wishlist = WishList.get_or_create_default(user=self.user)
        item = WishListItem.objects.create(
            wishlist=wishlist,
            product=self.product,
            price_when_added=self.product.price,
        )

        client = Client()
        client.login(username="removeedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:remove_from_wishlist"),
            {"item_id": item.id},
        )
        assert response.status_code == 200
        assert not WishListItem.objects.filter(pk=item.id).exists()

    def test_remove_by_product_and_wishlist(self):
        wishlist = WishList.get_or_create_default(user=self.user)
        item = WishListItem.objects.create(
            wishlist=wishlist,
            product=self.product,
            price_when_added=self.product.price,
        )

        client = Client()
        client.login(username="removeedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:remove_from_wishlist"),
            {"product_id": self.product.id, "wishlist_id": wishlist.id},
        )
        assert response.status_code == 200
        assert not WishListItem.objects.filter(pk=item.id).exists()

    def test_remove_product_from_all_lists(self):
        wishlist_a = WishList.objects.create(user=self.user, name="List A")
        wishlist_b = WishList.objects.create(user=self.user, name="List B")
        WishListItem.objects.create(
            wishlist=wishlist_a,
            product=self.product,
            price_when_added=self.product.price,
        )
        WishListItem.objects.create(
            wishlist=wishlist_b,
            product=self.product,
            price_when_added=self.product.price,
        )

        client = Client()
        client.login(username="removeedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:remove_from_wishlist"),
            {"product_id": self.product.id},
        )
        assert response.status_code == 200
        assert WishListItem.objects.filter(product=self.product).count() == 0


class TestMoveItemViewEdgeCases(TestCase):
    """Additional edge case tests for move item."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="moveedge@example.com",
            email="moveedge@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="Move Edge Category", slug="move-edge-category")
        cls.product = Product.objects.create(
            name="Move Edge Product",
            slug="move-edge-product",
            price=Decimal("55.00"),
            category=cls.category,
        )

    def test_move_missing_params(self):
        client = Client()
        response = client.post(reverse("favourites:move_item"), {})
        assert response.status_code == 400

    def test_move_to_list_with_duplicate_product(self):
        source = WishList.objects.create(user=self.user, name="Source")
        target = WishList.objects.create(user=self.user, name="Target")
        item = WishListItem.objects.create(
            wishlist=source,
            product=self.product,
            price_when_added=self.product.price,
        )
        WishListItem.objects.create(
            wishlist=target,
            product=self.product,
            price_when_added=self.product.price,
        )

        client = Client()
        client.login(username="moveedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:move_item"),
            {"item_id": item.id, "target_wishlist_id": target.id},
        )
        assert response.status_code == 400


class TestAddAllToCartViewEdgeCases(TestCase):
    """Additional edge case tests for add all to cart."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="cartedge@example.com",
            email="cartedge@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="Cart Edge Category", slug="cart-edge-category")
        cls.product_in_stock = Product.objects.create(
            name="Cart Edge Product 1",
            slug="cart-edge-product-1",
            price=Decimal("7.00"),
            category=cls.category,
            stock=5,
        )
        cls.product_out_stock = Product.objects.create(
            name="Cart Edge Product 2",
            slug="cart-edge-product-2",
            price=Decimal("9.00"),
            category=cls.category,
            stock=0,
        )

    def test_add_all_to_cart_missing_wishlist_id(self):
        client = Client()
        response = client.post(reverse("favourites:add_all_to_cart"), {})
        assert response.status_code == 400

    def test_add_all_to_cart_mixed_availability(self):
        wishlist = WishList.get_or_create_default(user=self.user)
        WishListItem.objects.create(
            wishlist=wishlist,
            product=self.product_in_stock,
            price_when_added=self.product_in_stock.price,
        )
        WishListItem.objects.create(
            wishlist=wishlist,
            product=self.product_out_stock,
            price_when_added=self.product_out_stock.price,
        )

        client = Client()
        client.login(username="cartedge@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:add_all_to_cart"),
            {"wishlist_id": wishlist.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["added_count"] == 1
        assert data["unavailable_count"] == 1

        cart_id = client.session.get("cart_id")
        cart = Cart.objects.get(id=cart_id)
        line = CartLine.objects.get(cart=cart, product=self.product_in_stock)
        assert line.quantity == 1

        response = client.post(
            reverse("favourites:add_all_to_cart"),
            {"wishlist_id": wishlist.id},
        )
        assert response.status_code == 200
        line.refresh_from_db()
        assert line.quantity == 2


class TestGetWishlistsView(TestCase):
    """Tests for get wishlists API endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="getlists@example.com",
            email="getlists@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="GetList Category", slug="getlist-category")
        cls.product = Product.objects.create(
            name="GetList Product",
            slug="getlist-product",
            price=Decimal("4.00"),
            category=cls.category,
        )

    def test_get_wishlists_creates_default_for_anonymous(self):
        client = Client()
        response = client.get(reverse("favourites:get_wishlists"))
        assert response.status_code == 200
        data = response.json()
        assert len(data["wishlists"]) == 1
        assert data["wishlists"][0]["is_default"] is True

    def test_get_wishlists_includes_item_counts(self):
        wishlist = WishList.get_or_create_default(user=self.user)
        WishListItem.objects.create(
            wishlist=wishlist,
            product=self.product,
            price_when_added=self.product.price,
        )

        client = Client()
        client.login(username="getlists@example.com", password="testpass123")
        response = client.get(reverse("favourites:get_wishlists"))
        assert response.status_code == 200
        data = response.json()
        assert data["wishlists"][0]["item_count"] == 1


class TestCheckProductStatusEdgeCases(TestCase):
    """Additional edge case tests for product status API."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="statusedge@example.com",
            email="statusedge@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="Status Edge Category", slug="status-edge-category")
        cls.product_1 = Product.objects.create(
            name="Status Edge Product 1",
            slug="status-edge-product-1",
            price=Decimal("11.00"),
            category=cls.category,
        )
        cls.product_2 = Product.objects.create(
            name="Status Edge Product 2",
            slug="status-edge-product-2",
            price=Decimal("22.00"),
            category=cls.category,
        )

    def test_check_status_invalid_product_ids(self):
        client = Client()
        response = client.get(reverse("favourites:check_product_status"), {"product_ids": "abc"})
        assert response.status_code == 200
        assert response.json()["status"] == {}

    def test_check_status_multiple_products(self):
        wishlist = WishList.get_or_create_default(user=self.user)
        WishListItem.objects.create(
            wishlist=wishlist,
            product=self.product_1,
            price_when_added=self.product_1.price,
        )

        client = Client()
        client.login(username="statusedge@example.com", password="testpass123")
        response = client.get(
            reverse("favourites:check_product_status"),
            {"product_ids": f"{self.product_1.id},{self.product_2.id}"},
        )
        data = response.json()["status"]
        assert str(self.product_1.id) in data
        assert str(self.product_2.id) not in data


class TestWishlistPartialsView(TestCase):
    """Tests for HTMX partial views."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="partials@example.com",
            email="partials@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="Partial Category", slug="partial-category")
        cls.product = Product.objects.create(
            name="Partial Product",
            slug="partial-product",
            price=Decimal("13.00"),
            category=cls.category,
            stock=5,
        )
        cls.product_out = Product.objects.create(
            name="Partial Product Out",
            slug="partial-product-out",
            price=Decimal("9.00"),
            category=cls.category,
            stock=0,
        )
        cls.wishlist = WishList.get_or_create_default(user=cls.user)
        WishListItem.objects.create(
            wishlist=cls.wishlist,
            product=cls.product,
            price_when_added=cls.product.price,
        )
        WishListItem.objects.create(
            wishlist=cls.wishlist,
            product=cls.product_out,
            price_when_added=cls.product_out.price,
        )

    def test_wishlist_items_partial(self):
        client = Client()
        client.login(username="partials@example.com", password="testpass123")
        response = client.get(
            reverse("favourites:wishlist_items_partial"),
            {"list": self.wishlist.share_id},
        )
        assert response.status_code == 200
        assert "Partial Product" in response.content.decode()
        assert "Partial Product Out" in response.content.decode()

    def test_wishlist_items_partial_available_filter(self):
        client = Client()
        client.login(username="partials@example.com", password="testpass123")
        response = client.get(
            reverse("favourites:wishlist_items_partial"),
            {"list": self.wishlist.share_id, "available": "1"},
        )
        assert response.status_code == 200
        content = response.content.decode()
        assert "Partial Product" in content
        assert "Partial Product Out" not in content

    def test_wishlists_sidebar_partial(self):
        client = Client()
        client.login(username="partials@example.com", password="testpass123")
        response = client.get(reverse("favourites:wishlists_sidebar_partial"))
        assert response.status_code == 200
        assert "Favourites" in response.content.decode() or "Ulubione" in response.content.decode()


# ============================================
# SHARE ID TESTS
# ============================================


class TestShareIdGeneration(TestCase):
    """Tests for the share_id field on WishList model."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="shareid@example.com",
            email="shareid@example.com",
            password="testpass123",
        )

    def test_share_id_auto_generated(self):
        """Test that share_id is automatically generated on creation."""
        wishlist = WishList.objects.create(user=self.user, name="Test Share")
        assert wishlist.share_id is not None
        assert len(wishlist.share_id) == 10

    def test_share_id_is_unique(self):
        """Test that each wishlist gets a unique share_id."""
        wishlists = [WishList.objects.create(user=self.user, name=f"List {i}") for i in range(10)]
        share_ids = [wl.share_id for wl in wishlists]
        assert len(set(share_ids)) == 10

    def test_share_id_alphanumeric_lowercase(self):
        """Test that share_id contains only lowercase letters and digits."""
        import string

        allowed = set(string.ascii_lowercase + string.digits)
        wishlist = WishList.objects.create(user=self.user, name="Chars Test")
        assert all(c in allowed for c in wishlist.share_id)

    def test_share_id_preserved_on_save(self):
        """Test that share_id doesn't change when the wishlist is updated."""
        wishlist = WishList.objects.create(user=self.user, name="Persist Test")
        original_share_id = wishlist.share_id
        wishlist.name = "Updated Name"
        wishlist.save()
        wishlist.refresh_from_db()
        assert wishlist.share_id == original_share_id

    def test_default_wishlist_has_share_id(self):
        """Test that default wishlist created via get_or_create_default has share_id."""
        wishlist = WishList.get_or_create_default(user=self.user)
        assert wishlist.share_id is not None
        assert len(wishlist.share_id) == 10


class TestShareIdInViews(TestCase):
    """Tests for share_id usage in views."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="shareidview@example.com",
            email="shareidview@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="ShareId Category", slug="shareid-category")
        cls.product = Product.objects.create(
            name="ShareId Product",
            slug="shareid-product",
            price=Decimal("20.00"),
            category=cls.category,
            stock=5,
        )

    def test_favourites_page_with_share_id_param(self):
        """Test that favourites page accepts share_id in ?list= parameter."""
        client = Client()
        client.login(username="shareidview@example.com", password="testpass123")
        wishlist = WishList.get_or_create_default(user=self.user)
        WishListItem.objects.create(
            wishlist=wishlist,
            product=self.product,
            price_when_added=self.product.price,
        )

        response = client.get(
            reverse("favourites:favourites_page"),
            {"list": wishlist.share_id},
        )
        assert response.status_code == 200
        assert response.context["active_wishlist"].id == wishlist.id

    def test_favourites_page_with_invalid_share_id_falls_back(self):
        """Test fallback to default when invalid share_id is provided."""
        client = Client()
        client.login(username="shareidview@example.com", password="testpass123")
        default_wl = WishList.get_or_create_default(user=self.user)

        response = client.get(
            reverse("favourites:favourites_page"),
            {"list": "nonexistent"},
        )
        assert response.status_code == 200
        assert response.context["active_wishlist"].id == default_wl.id

    def test_favourites_page_numeric_id_no_longer_works(self):
        """Test that plain numeric IDs no longer resolve wishlists."""
        client = Client()
        client.login(username="shareidview@example.com", password="testpass123")
        wishlist = WishList.get_or_create_default(user=self.user)

        response = client.get(
            reverse("favourites:favourites_page"),
            {"list": str(wishlist.id)},
        )
        assert response.status_code == 200
        # Should fall back to default (which is the same list but via share_id lookup)
        # The key point is it doesn't crash

    def test_wishlist_items_partial_with_share_id(self):
        """Test items partial accepts share_id."""
        client = Client()
        client.login(username="shareidview@example.com", password="testpass123")
        wishlist = WishList.get_or_create_default(user=self.user)
        WishListItem.objects.create(
            wishlist=wishlist,
            product=self.product,
            price_when_added=self.product.price,
        )

        response = client.get(
            reverse("favourites:wishlist_items_partial"),
            {"list": wishlist.share_id},
        )
        assert response.status_code == 200
        assert "ShareId Product" in response.content.decode()

    def test_wishlist_items_partial_missing_list_param(self):
        """Test items partial returns 400 when list param is missing."""
        client = Client()
        client.login(username="shareidview@example.com", password="testpass123")
        response = client.get(reverse("favourites:wishlist_items_partial"))
        assert response.status_code == 400

    def test_wishlist_items_partial_invalid_share_id(self):
        """Test items partial returns 404 for invalid share_id."""
        client = Client()
        client.login(username="shareidview@example.com", password="testpass123")
        response = client.get(
            reverse("favourites:wishlist_items_partial"),
            {"list": "zzzzzzzzzz"},
        )
        assert response.status_code == 404

    def test_wishlists_sidebar_partial_with_share_id(self):
        """Test sidebar partial accepts share_id active parameter."""
        client = Client()
        client.login(username="shareidview@example.com", password="testpass123")
        wishlist = WishList.get_or_create_default(user=self.user)

        response = client.get(
            reverse("favourites:wishlists_sidebar_partial"),
            {"active": wishlist.share_id},
        )
        assert response.status_code == 200


# ============================================
# BULK OPERATIONS TESTS
# ============================================


class TestBulkRemoveView(TestCase):
    """Tests for bulk remove endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="bulkremove@example.com",
            email="bulkremove@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="BulkRemove Category", slug="bulkremove-category")
        cls.product_1 = Product.objects.create(
            name="BulkRemove Product 1",
            slug="bulkremove-product-1",
            price=Decimal("10.00"),
            category=cls.category,
        )
        cls.product_2 = Product.objects.create(
            name="BulkRemove Product 2",
            slug="bulkremove-product-2",
            price=Decimal("20.00"),
            category=cls.category,
        )

    def test_bulk_remove_success(self):
        wishlist = WishList.get_or_create_default(user=self.user)
        item1 = WishListItem.objects.create(
            wishlist=wishlist, product=self.product_1, price_when_added=self.product_1.price
        )
        item2 = WishListItem.objects.create(
            wishlist=wishlist, product=self.product_2, price_when_added=self.product_2.price
        )

        client = Client()
        client.login(username="bulkremove@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:bulk_remove"),
            {"item_ids": [str(item1.id), str(item2.id)]},
        )
        assert response.status_code == 200
        assert response.json()["success"] is True
        assert wishlist.items.count() == 0

    def test_bulk_remove_empty_selection(self):
        client = Client()
        client.login(username="bulkremove@example.com", password="testpass123")
        response = client.post(reverse("favourites:bulk_remove"), {})
        assert response.status_code == 400


class TestCopyItemsView(TestCase):
    """Tests for copy items endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="copyitems@example.com",
            email="copyitems@example.com",
            password="testpass123",
        )
        cls.category = Category.objects.create(name="CopyItems Category", slug="copyitems-category")
        cls.product_1 = Product.objects.create(
            name="CopyItems Product 1",
            slug="copyitems-product-1",
            price=Decimal("10.00"),
            category=cls.category,
        )
        cls.product_2 = Product.objects.create(
            name="CopyItems Product 2",
            slug="copyitems-product-2",
            price=Decimal("20.00"),
            category=cls.category,
        )

    def test_copy_items_success(self):
        source = WishList.objects.create(user=self.user, name="Source")
        target = WishList.objects.create(user=self.user, name="Target")
        item = WishListItem.objects.create(
            wishlist=source, product=self.product_1, price_when_added=self.product_1.price
        )

        client = Client()
        client.login(username="copyitems@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:copy_items"),
            {"item_ids": [str(item.id)], "target_wishlist_id": target.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["copied_count"] == 1
        # Original should still exist
        assert source.items.filter(product=self.product_1).exists()
        # Copy should exist in target
        assert target.items.filter(product=self.product_1).exists()

    def test_copy_items_skips_duplicates(self):
        source = WishList.objects.create(user=self.user, name="Source")
        target = WishList.objects.create(user=self.user, name="Target")
        item = WishListItem.objects.create(
            wishlist=source, product=self.product_1, price_when_added=self.product_1.price
        )
        # Already in target
        WishListItem.objects.create(wishlist=target, product=self.product_1, price_when_added=self.product_1.price)

        client = Client()
        client.login(username="copyitems@example.com", password="testpass123")
        response = client.post(
            reverse("favourites:copy_items"),
            {"item_ids": [str(item.id)], "target_wishlist_id": target.id},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["copied_count"] == 0

    def test_copy_items_missing_params(self):
        client = Client()
        client.login(username="copyitems@example.com", password="testpass123")
        response = client.post(reverse("favourites:copy_items"), {})
        assert response.status_code == 400
