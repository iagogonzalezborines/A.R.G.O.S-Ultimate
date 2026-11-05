import unittest

from proof_value import value


class ProofValueTest(unittest.TestCase):
    def test_value_is_42(self):
        self.assertEqual(value(), 42)


if __name__ == "__main__":
    unittest.main()
