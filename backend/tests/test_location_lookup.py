import unittest

from app.services.location_match import place_contains_area


class LocationLookupTests(unittest.TestCase):
    def test_city_matches_any_exact_place_component(self):
        self.assertTrue(
            place_contains_area("Dharampeth, Nagpur, Maharashtra, India", "nagpur", "city")
        )
        self.assertFalse(
            place_contains_area("Ashti, Maharashtra, India", "Nagpur", "city")
        )

    def test_district_requires_the_district_to_be_named_in_the_photo(self):
        self.assertTrue(
            place_contains_area("Ashti, Beed, Maharashtra, India", "Beed", "district")
        )
        self.assertIsNone(
            place_contains_area("Ashti, Beed, Maharashtra, India", "Nagpur", "district")
        )
        self.assertIsNone(
            place_contains_area("Ashti, Maharashtra, India", "Beed", "district")
        )

    def test_missing_location_data_is_not_treated_as_a_match(self):
        self.assertIsNone(place_contains_area(None, "Nagpur", "city"))
        self.assertIsNone(place_contains_area("Ashti, Maharashtra", None, "city"))
