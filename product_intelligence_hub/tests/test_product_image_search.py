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

    def test_product_image_change_marks_index_pending(self):
        product = self.env["product.template"].create(
            {"name": "Image search test product", "sale_ok": True}
        )
        product.with_context(pi_skip_image_search_dirty=True).write(
            {"pi_image_search_state": "indexed"}
        )
        product.write({"image_1920": base64.b64encode(self._image_bytes())})
        self.assertEqual(product.pi_image_search_state, "pending")
