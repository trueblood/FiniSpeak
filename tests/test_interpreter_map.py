import math
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.geo_service import encode_geohash, geocode_public_area, geohash_prefixes, haversine_miles


ROOT = Path(__file__).resolve().parents[1]


class GeographicSearchTests(unittest.TestCase):
    def test_haversine_distance_filters_a_known_radius(self):
        indianapolis = (39.7684, -86.1581)
        bloomington = (39.1653, -86.5264)
        distance = haversine_miles(*indianapolis, *bloomington)
        self.assertGreater(distance, 40)
        self.assertLess(distance, 50)

    def test_geohash_is_stable_and_prefix_search_is_bounded(self):
        self.assertEqual(encode_geohash(39.7684, -86.1581, 6), "dp4dpr")
        prefixes = geohash_prefixes(39.7684, -86.1581, 25)
        self.assertGreaterEqual(len(prefixes), 1)
        self.assertLessEqual(len(prefixes), 16)
        self.assertTrue(all(len(prefix) == 3 for prefix in prefixes))

    @patch("services.geo_service.urlopen")
    def test_manual_location_returns_approximate_coordinates(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'[{"lat":"39.768456","lon":"-86.158123","display_name":"Indianapolis, Indiana","address":{"city":"Indianapolis","state":"Indiana","country":"United States"}}]'
        urlopen.return_value = response
        location = geocode_public_area("Indianapolis, IN")
        self.assertEqual(location["latitude"], 39.768)
        self.assertEqual(location["city"], "Indianapolis")
        self.assertNotIn("address", location)

    @patch("services.geo_service.urlopen")
    def test_residential_address_is_rejected(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'[{"lat":"39.7","lon":"-86.1","address":{"house_number":"123","road":"Private St","city":"Indianapolis"}}]'
        urlopen.return_value = response
        with self.assertRaisesRegex(ValueError, "not a street address"):
            geocode_public_area("123 Private St")


class MapUiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "views/templates/index.html").read_text()
        cls.javascript = (ROOT / "views/static/js/app.js").read_text()
        cls.css = (ROOT / "views/static/css/style.css").read_text()

    def test_location_permission_has_manual_fallback(self):
        self.assertIn("navigator.geolocation.getCurrentPosition", self.javascript)
        self.assertIn('id="manualLocationForm"', self.html)
        self.assertIn("Location permission was denied", self.javascript)

    def test_map_and_profile_selection_are_synchronized(self):
        self.assertIn("directoryMarkers.get(profile.id)", self.javascript)
        self.assertIn('data-interpreter-id="${CSS.escape(profile.id)}"', self.javascript)
        self.assertIn("marker.openPopup()", self.javascript)

    def test_remote_profiles_do_not_require_map_coordinates(self):
        self.assertIn('option value="remote">Remote video', self.html)
        self.assertIn("if (!location?.showOnMap", self.javascript)
        self.assertIn("Nearby search is temporarily unavailable", self.javascript)

    def test_mobile_map_layout_is_responsive(self):
        self.assertIn("#interpreterMap { min-height:55vh", self.css)
        self.assertIn("#directorySplitView { display:none", self.css)

    def test_map_has_local_leaflet_layout_fallback(self):
        self.assertIn("#interpreterMap .leaflet-pane", self.css)
        self.assertIn("#interpreterMap .leaflet-tile { width:256px; height:256px", self.css)
        self.assertIn("directoryMap.invalidateSize({ pan: false })", self.javascript)
        self.assertIn("sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=", self.html)

    def test_interpreter_location_is_part_of_profile_workflow(self):
        self.assertIn('data-wizard-step="4"', self.html)
        self.assertIn('data-wizard-panel="3"', self.html)
        self.assertIn("Service location", self.html)
        self.assertIn('id="publicProfileLocation"', self.html)

    def test_map_can_be_hidden_and_location_filters_can_be_cleared(self):
        self.assertIn('id="hideDirectoryMap"', self.html)
        self.assertIn('id="showAllInterpreters"', self.html)
        self.assertIn('$("hideDirectoryMap").onclick = () => setDirectoryView("list")', self.javascript)
        self.assertIn("async function showAllInterpreters()", self.javascript)
        self.assertIn("directoryOrigin = null", self.javascript)
        self.assertIn('$("directoryRadius").value = "anywhere"', self.javascript)


if __name__ == "__main__":
    unittest.main()
