import base64
import math
from io import BytesIO

from PIL import Image

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestProductImageSearch(TransactionCase):

    @staticmethod
    def _image_bytes():
        output = BytesIO()
        Image.new("RGB", (64, 48), "#68465f").save(output, format="PNG")
        return output.getvalue()

    def test_uploaded_image_is_normalized_for_qdrant(self):
        data_url, digest = self.env["product.image.search.service"]._prepare_image(
            self._image_bytes()
        )
        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        self.assertEqual(len(digest), 64)

    def test_local_visual_vector_is_normalized_and_has_configured_dimension(self):
        service = self.env["product.image.search.service"]
        data_url, _digest = service._prepare_image(self._image_bytes())
        vector = service._local_image_vector(
            base64.b64decode(data_url.split(",", 1)[1])
        )
        self.assertEqual(len(vector), 512)
        self.assertAlmostEqual(
            math.sqrt(sum(value * value for value in vector)), 1.0, places=6
        )

    def test_non_image_upload_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.env["product.image.search.service"]._prepare_image(b"not-an-image")

    def test_odoo_image_decoder_accepts_raw_and_base64_images(self):
        service = self.env["product.image.search.service"]
        image_bytes = self._image_bytes()
        encoded = base64.b64encode(image_bytes)

        self.assertEqual(service._decode_odoo_image(image_bytes), image_bytes)
        self.assertEqual(service._decode_odoo_image(encoded), image_bytes)
        self.assertEqual(
            service._decode_odoo_image(
                "data:image/png;base64," + encoded.decode("ascii")
            ),
            image_bytes,
        )

    def test_relevance_filter_removes_low_score_false_positives(self):
        service = self.env["product.image.search.service"]
        points = [
            {"score": 1.0, "payload": {"product_tmpl_id": 9}},
            {"score": 0.578, "payload": {"product_tmpl_id": 13}},
            {"score": 0.549, "payload": {"product_tmpl_id": 14}},
        ]
        config = {"score_threshold": 0.18, "result_limit": 12}

        self.assertEqual(service._relevant_product_ids(points, config), [9])

    def test_relevance_filter_keeps_close_similar_products(self):
        service = self.env["product.image.search.service"]
        points = [
            {"score": 0.78, "payload": {"product_tmpl_id": 9}},
            {"score": 0.76, "payload": {"product_tmpl_id": 10}},
            {"score": 0.71, "payload": {"product_tmpl_id": 11}},
            {"score": 0.70, "payload": {"product_tmpl_id": 9}},
        ]
        config = {"score_threshold": 0.18, "result_limit": 12}

        self.assertEqual(service._relevant_product_ids(points, config), [9, 10])

    def test_relevance_filter_returns_nothing_for_weak_matches(self):
        service = self.env["product.image.search.service"]
        points = [{"score": 0.62, "payload": {"product_tmpl_id": 9}}]
        config = {"score_threshold": 0.18, "result_limit": 12}

        self.assertEqual(service._relevant_product_ids(points, config), [])

    def test_product_image_change_marks_index_pending(self):
        product = self.env["product.template"].create(
            {"name": "Image search test product", "sale_ok": True}
        )
        product.with_context(pi_skip_image_search_dirty=True).write(
            {"pi_image_search_state": "indexed"}
        )
        product.write({"image_1920": base64.b64encode(self._image_bytes())})
        self.assertEqual(product.pi_image_search_state, "pending")
