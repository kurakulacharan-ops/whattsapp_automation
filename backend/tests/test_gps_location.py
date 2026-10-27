import gzip
import hashlib
import unittest
from unittest.mock import patch
from app.services.location_lookup import lookup_district, same_district, DATA_PATH, _districts


def feature(name, identifier, rings):
    outer = rings[0]
    return ({"shapeName": name, "shapeID": identifier}, rings, (min(p[0] for p in outer), min(p[1] for p in outer), max(p[0] for p in outer), max(p[1] for p in outer)))


class OfflineDistrictTests(unittest.TestCase):
    def test_packaged_data_integrity(self):
        self.assertEqual(hashlib.sha256(gzip.decompress(DATA_PATH.read_bytes())).hexdigest(), "8bef6929fd65432e7dc775e7c44473e84efff064ebddbfd6b834e6291546db40")

    def test_real_points_offline(self):
        with patch("socket.socket", side_effect=AssertionError("Network forbidden")):
            ashti = lookup_district(18.804759, 75.174791)
            beed = lookup_district(18.9891, 75.7601)
            nagpur = lookup_district(21.1458, 79.0882)
        self.assertEqual(ashti["status"], "resolved")
        self.assertEqual(nagpur["district"], "Nagpur")
        self.assertTrue(same_district(ashti, beed))
        self.assertFalse(same_district(ashti, nagpur))

    def test_names_do_not_control_comparison(self):
        area = lookup_district(18.804759, 75.174791)
        self.assertTrue(same_district(area, {**area, "district": "Beed District alternate spelling"}))
        self.assertFalse(same_district(area, {**area, "district_id": "other"}))
        self.assertIsNone(same_district(area, {**area, "dataset_id": "other-version"}))

    def test_invalid_and_uncovered_points(self):
        for lat, lon in [(float("nan"), 75), (91, 75), (18, 181)]:
            self.assertEqual(lookup_district(lat, lon)["status"], "invalid_coordinates")
        self.assertEqual(lookup_district(0, 0)["status"], "outside_coverage")

    def test_holes_boundaries_and_overlap(self):
        outer = [[70, 20], [71, 20], [71, 21], [70, 21], [70, 20]]
        hole = [[70.4, 20.4], [70.6, 20.4], [70.6, 20.6], [70.4, 20.6], [70.4, 20.4]]
        district = feature("A", "a", [outer, hole])
        with patch("app.services.location_lookup._districts", return_value=[district]):
            self.assertEqual(lookup_district(20.2, 70.2)["status"], "resolved")
            self.assertEqual(lookup_district(20.5, 70.5)["status"], "outside_coverage")
            for point in [(20.5, 70), (20.5, 70.0005), (20.5, 69.9995), (20.4, 70.5)]:
                self.assertEqual(lookup_district(*point)["status"], "boundary_uncertain")
        with patch("app.services.location_lookup._districts", return_value=[district, feature("B", "b", [outer])]):
            self.assertEqual(lookup_district(20.2, 70.2)["status"], "ambiguous")
        with patch("app.services.location_lookup._districts", return_value=[district, district]):
            self.assertEqual(lookup_district(20.2, 70.2)["status"], "resolved")

    def test_missing_dataset_is_unverified(self):
        with patch("app.services.location_lookup._districts", side_effect=FileNotFoundError):
            result = lookup_district(18.8, 75.1)
        self.assertEqual(result["status"], "dataset_unavailable")
        self.assertIsNone(same_district(result, result))


if __name__ == "__main__":
    unittest.main()
