from dataclasses import replace
import tomllib

from totalmarker.config import load
from totalmarker.errors import ConfigError, StorageError
from .support import PROJECT, Sandbox


class CloudTemplateTests(Sandbox):
    def load_text(self, text):
        (self.root / "templates.toml").write_text(text)
        return load(self.fs, "templates.toml")

    def example(self, provider="custom"):
        text = (PROJECT / "dev/examples/custom.example.toml").read_text()
        return text.replace('provider = "custom"', 'provider = "' + provider + '"', 1)

    def test_one_resolution_changes_url_and_local_output_for_both_providers(self):
        for provider in ("xeric", "custom"):
            original = self.example(provider)
            for resolution in (2048, 4096, 8192):
                with self.subTest(provider=provider, resolution=resolution):
                    text = original.replace("resolution = 4096",
                                            "resolution = " + str(resolution), 1)
                    settings = self.load_text(text)
                    name = f"clouds-{resolution}.jpg"
                    self.assertTrue(settings.url.endswith("/" + name))
                    self.assertEqual(settings.image, "images/" + name)
                    if provider == "xeric":
                        self.assertIn(f"/{resolution}/", settings.url)
                    self.assertEqual((self.root / "templates.toml").read_text(), text)

    def test_custom_8096_is_not_restricted_to_xeric_widths_or_silently_changed(self):
        text = self.example().replace("resolution = 4096", "resolution = 8096", 1)
        settings = self.load_text(text)
        self.assertEqual(settings.resolution, 8096)
        self.assertTrue(settings.url.endswith("/clouds-8096.jpg"))
        self.assertTrue(settings.image.endswith("/clouds-8096.jpg"))
        with self.assertRaisesRegex(ConfigError, "2048, 4096 or 8192"):
            self.load_text(text.replace('provider = "custom"', 'provider = "xeric"', 1))

    def test_literal_custom_urls_filenames_and_output_paths_remain_supported(self):
        text = self.example().replace(
            "https://cloud.example.invalid/clouds-{resolution}.jpg",
            "https://cloud.example.invalid/current.jpg").replace(
            'local_image_name_template = "clouds-{resolution}.jpg"',
            'local_image_name_template = "my-cloud-map.jpg"')
        settings = self.load_text(text)
        self.assertTrue(settings.url.endswith("/current.jpg"))
        self.assertEqual(settings.image, "images/my-cloud-map.jpg")
        settings = self.load_text(text.replace(
            'image = "images/{local_image_name}"',
            'image = "images/special/literal.jpg"'))
        self.assertEqual(settings.image, "images/special/literal.jpg")

    def test_url_can_use_shared_local_filename_token(self):
        text = self.example().replace(
            "https://cloud.example.invalid/clouds-{resolution}.jpg",
            "https://cloud.example.invalid/{local_image_name}")
        self.assertTrue(self.load_text(text).url.endswith("/clouds-4096.jpg"))

    def test_switch_selects_only_selected_provider_credentials_and_auth_mode(self):
        text = self.example().replace('auth_mode = "none"', 'auth_mode = "basic"', 1)
        text = text.replace('username = ""', 'username = "DUMMY_XERIC_USER"', 1)
        text = text.replace('password = ""', 'password = "DUMMY_XERIC_PASSWORD"', 1)
        head, tail = text.split("[cloud.custom]", 1)
        tail = tail.replace('username = ""', 'username = "DUMMY_CUSTOM_USER"', 1)
        tail = tail.replace('password = ""', 'password = "DUMMY_CUSTOM_PASSWORD"', 1)
        text = head + "[cloud.custom]" + tail
        custom = self.load_text(text)
        xeric = self.load_text(text.replace(
            'provider = "custom"', 'provider = "xeric"', 1))
        self.assertEqual(custom.auth.resolve({}), ("DUMMY_CUSTOM_USER", "DUMMY_CUSTOM_PASSWORD"))
        self.assertEqual(xeric.auth.resolve({}), ("DUMMY_XERIC_USER", "DUMMY_XERIC_PASSWORD"))
        self.assertNotIn("DUMMY", repr(custom))
        self.assertNotIn("DUMMY", repr(xeric))

    def test_anonymous_custom_does_not_resolve_inactive_xeric_environment(self):
        text = self.example().replace(
            'username_env = ""', 'username_env = "DUMMY_UNAVAILABLE_XERIC_USER"', 1).replace(
            'password_env = ""', 'password_env = "DUMMY_UNAVAILABLE_XERIC_PASSWORD"', 1)
        self.assertIsNone(self.load_text(text).auth.resolve({}))

    def test_unsupported_or_malformed_placeholders_are_rejected_even_if_inactive(self):
        for value in ("{DUMMY_UNKNOWN}", "{resolution:04d}", "{resolution!r}",
                      "{resolution.__class__}", "{resolution[0]}",
                      "{{resolution}}", "{resolution", "resolution}"):
            for location in ("filename", "custom", "xeric", "output"):
                with self.subTest(value=value, location=location):
                    text = self.example()
                    if location == "filename":
                        text = text.replace('local_image_name_template = "clouds-{resolution}.jpg"',
                                            'local_image_name_template = "' + value + '.jpg"')
                    elif location == "custom":
                        text = text.replace("cloud.example.invalid/clouds-{resolution}.jpg",
                                            "cloud.example.invalid/" + value + ".jpg")
                    elif location == "xeric":
                        text = text.replace("xplanet/clouds/{resolution}/clouds-{resolution}.jpg",
                                            "xplanet/clouds/" + value + ".jpg")
                    else:
                        text = text.replace('image = "images/{local_image_name}"',
                                            'image = "output/' + value + '.jpg"')
                    with self.assertRaises(ConfigError) as error:
                        self.load_text(text)
                    self.assertNotIn("DUMMY", str(error.exception))

    def test_native_template_and_resolution_types_are_checked(self):
        changes = [
            ('resolution = 4096', 'resolution = true'),
            ('resolution = 4096', 'resolution = "4096"'),
            ('resolution = 4096', 'resolution = 4096.0'),
            ('local_image_name_template = "clouds-{resolution}.jpg"',
             'local_image_name_template = 4096'),
            ('url_template = "https://cloud.example.invalid/clouds-{resolution}.jpg"',
             'url_template = ["DUMMY_INVALID"]'),
            ('image = "images/{local_image_name}"', 'image = false'),
            ('username = ""', 'username = 123'),
        ]
        for old, new in changes:
            with self.subTest(new=new):
                with self.assertRaisesRegex(ConfigError, "wrong type"):
                    self.load_text(self.example().replace(old, new, 1))

    def test_expanded_output_containment_and_filename_rules_are_checked(self):
        text = self.example()
        for old, new in [
            ('local_image_name_template = "clouds-{resolution}.jpg"',
             'local_image_name_template = "../clouds-{resolution}.jpg"'),
            ('image = "images/{local_image_name}"',
             'image = "../{local_image_name}"'),
            ('image = "images/{local_image_name}"',
             'image = "reference/{local_image_name}"')]:
            with self.subTest(new=new):
                with self.assertRaises((ConfigError, StorageError)):
                    self.load_text(text.replace(old, new, 1))

    def test_xeric_template_cannot_send_xeric_auth_to_custom_origin(self):
        with self.assertRaisesRegex(ConfigError, "secure.xericdesign.com"):
            self.load_text(self.example().replace(
                "https://secure.xericdesign.com/xplanet",
                "https://cloud.example.invalid/xplanet", 1))

    def test_legacy_ini_literals_and_explicit_templates_are_supported(self):
        text = ("CloudProvider=custom\nCloudResolution=8096\n"
                "CloudURL=https://cloud.example.invalid/current.jpg\n"
                "CloudLocalImageName=literal.jpg\n")
        (self.root / "config.ini").write_text(text)
        settings = load(self.fs, "config.ini")
        self.assertTrue(settings.url.endswith("/current.jpg"))
        self.assertEqual(settings.image, "images/literal.jpg")
        self.assertEqual((self.root / "config.ini").read_text(), text)
        text = text.replace("current.jpg", "clouds-{resolution}.jpg").replace(
            "literal.jpg", "clouds-{resolution}.jpg") + "CloudOutput=images/{local_image_name}\n"
        (self.root / "config.ini").write_text(text)
        settings = load(self.fs, "config.ini")
        self.assertTrue(settings.url.endswith("/clouds-8096.jpg"))
        self.assertEqual(settings.image, "images/clouds-8096.jpg")

    def test_zero_resolution_allows_literals_but_not_resolution_templates(self):
        text = self.example().replace("resolution = 4096", "resolution = 0", 1)
        with self.assertRaisesRegex(ConfigError, "positive CloudResolution"):
            self.load_text(text)
        text = text.replace("clouds-{resolution}.jpg", "literal.jpg")
        settings = self.load_text(text)
        self.assertEqual(settings.resolution, 0)
        self.assertTrue(settings.url.endswith("/literal.jpg"))

    def test_duplicate_old_and_new_filename_or_custom_url_names_are_rejected(self):
        for text in [
            self.example().replace(
                'local_image_name_template = "clouds-{resolution}.jpg"',
                'local_image_name_template = "clouds-{resolution}.jpg"\nlocal_image_name = "literal.jpg"'),
            self.example().replace(
                'provider = "custom"',
                'provider = "custom"\nurl = "https://cloud.example.invalid/old.jpg"', 1)]:
            with self.assertRaises(ConfigError):
                self.load_text(text)

    def test_both_safe_toml_examples_include_both_providers_and_shared_settings(self):
        for name in ("custom.example.toml", "xeric.example.toml"):
            doc = tomllib.loads((PROJECT / "dev" / "examples" / name).read_text())
            self.assertIn("xeric", doc["cloud"])
            self.assertIn("custom", doc["cloud"])
            self.assertEqual(doc["cloud"]["resolution"], 4096)
            self.assertNotIn("4096", doc["cloud"]["local_image_name_template"])
            self.assertEqual(doc["paths"]["image"], "images/{local_image_name}")
            for provider in ("xeric", "custom"):
                self.assertIn("url_template", doc["cloud"][provider])
                self.assertIn("auth_mode", doc["cloud"][provider])
