"""Known logout regression must be rejected before building or installing files."""
import unittest
from unittest.mock import patch

import generalized
from generalized import GeneralizedEngine, OUTFIT_REGRESSION


class OutfitRegressionTests(unittest.TestCase):
    def setUp(self):
        # Deliberately mark pairs available: the final guard must not depend on
        # cached UI capability flags or require access to an installed game.
        self.engine = object.__new__(GeneralizedEngine)
        ids = (3400100, 3400117, 3402600, 3402628)
        self.engine.items = {
            f'outfit:{i}': {'key': f'outfit:{i}', 'id': i, 'c': 'outfit',
                            'support': {'available': True, 'reason': None}}
            for i in ids
        }
        self.pairs = [
            {'source': 'outfit:3400100', 'target': 'outfit:3400117', 'hero': 1000004},
            {'source': 'outfit:3402600', 'target': 'outfit:3402628', 'hero': 1000027},
        ]

    def test_disabled_in_picker(self):
        for item in self.engine.items.values():
            self.assertEqual(self.engine.intrinsic(item), OUTFIT_REGRESSION)

    def test_cached_available_pair_cannot_bypass_validation(self):
        for pair in self.pairs:
            with self.assertRaisesRegex(ValueError, 'reintroduced logout'):
                self.engine.validate([pair])

    def test_rejected_before_base_compile_or_session(self):
        with patch.object(generalized.Engine, 'build') as basic, \
                patch.object(generalized, 'Session') as session:
            with self.assertRaisesRegex(ValueError, 'reintroduced logout'):
                self.engine.build(self.pairs)
            basic.assert_not_called()
            session.assert_not_called()

    def test_rejected_before_apply_lock_or_file_access(self):
        # This fake engine has no mutex, state path or game path. Rejection must
        # happen before any of those install-time objects are accessed.
        with patch.object(generalized, 'Trial') as trial:
            with self.assertRaisesRegex(ValueError, 'reintroduced logout'):
                self.engine.apply(self.pairs)
            trial.assert_not_called()

    def test_direct_recipe_and_outfit_entry_points_are_blocked(self):
        with self.assertRaisesRegex(ValueError, 'reintroduced logout'):
            self.engine.recipes(self.pairs[0])
        with self.assertRaisesRegex(ValueError, 'reintroduced logout'):
            self.engine._outfit(None, None, None, None, None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
