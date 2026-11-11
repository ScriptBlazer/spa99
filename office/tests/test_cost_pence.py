"""cost_pence: an assistant cost stored in pence, shown in pounds to three places, half up."""
from django.test import SimpleTestCase

from office.templatetags.office_tags import cost_pence


class CostPenceTests(SimpleTestCase):
    def test_the_examples(self):
        self.assertEqual(cost_pence("0.35"), "£0.004")
        self.assertEqual(cost_pence("2.10"), "£0.021")
        self.assertEqual(cost_pence("123.4"), "£1.234")

    def test_half_rounds_up_and_zero_reads_as_zero(self):
        self.assertEqual(cost_pence("0.05"), "£0.001")   # 0.0005 pounds
        self.assertEqual(cost_pence("0.15"), "£0.002")   # 0.0015
        self.assertEqual(cost_pence("0.04"), "£0.000")
        self.assertEqual(cost_pence(0), "£0.000")

    def test_a_non_number_is_empty_and_thousands_get_a_comma(self):
        self.assertEqual(cost_pence("not a number"), "")
        self.assertEqual(cost_pence(None), "")
        self.assertEqual(cost_pence("123456789"), "£1,234,567.890")
