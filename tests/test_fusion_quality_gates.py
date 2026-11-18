"""Safety regression tests for uncertain AIS association, no detector required."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from sonarnet.config import RunConfig
from sonarnet.fusion.matching import Detection, SARAISFusion
from sonarnet.fusion.kalman import KalmanEstimate, ConstantVelocityKalman, linear_interpolate_to_time


def detection(x=0, i=0):
    return Detection(i, 0., x / 111195., 80., 20., (0, 0, 8, 2))


def estimate(x=0, gap=0, sigma=20):
    return KalmanEstimate(0., x / 111195., 0., 0., sigma, gap, 5)


class QualityGates(unittest.TestCase):
    def setUp(self):
        self.fusion = SARAISFusion(RunConfig())

    def test_close_but_stale_is_rejected(self):
        matches, _, reasons = self.fusion.match_with_reasons([detection()], {1: estimate(gap=181)})
        self.assertEqual(matches, {})
        self.assertEqual(reasons, ['stale_ais'])

    def test_close_but_uncertain_is_rejected(self):
        for sigma, reason in [(151, 'uncertain_position'), (float('nan'), 'invalid_ais')]:
            matches, _, reasons = self.fusion.match_with_reasons([detection()], {1: estimate(sigma=sigma)})
            self.assertEqual(matches, {})
            self.assertEqual(reasons, [reason])

    def test_fresh_confident_match_and_boundary(self):
        matches, _, reasons = self.fusion.match_with_reasons([detection(20)], {1: estimate(gap=180, sigma=150)})
        self.assertEqual(matches, {0: 1})
        self.assertEqual(reasons, ['matched'])

    def test_sigma_gate_rejects_distance_inside_legacy_cap(self):
        self.assertEqual(self.fusion.match_with_reasons([detection(200)], {1: estimate()})[2], ['out_of_range'])

    def test_no_ais_is_not_a_match(self):
        self.assertEqual(self.fusion.match_with_reasons([detection()], {})[2], ['no_ais'])

    def test_crossing_abstains_for_both(self):
        result = self.fusion.match_with_reasons([detection(-5), detection(5, 1)], {1: estimate(-5), 2: estimate(5)})
        self.assertEqual(result[0], {})
        self.assertEqual(result[2], ['ambiguous', 'ambiguous'])

    def test_two_detections_competing_for_one_ais_abstain(self):
        self.assertEqual(self.fusion.match_with_reasons([detection(-5), detection(5)], {1: estimate()})[2], ['ambiguous', 'ambiguous'])

    def test_separated_tracks_remain_unique(self):
        result = self.fusion.match_with_reasons([detection(), detection(300, 1)], {1: estimate(10), 2: estimate(310)})
        self.assertEqual(result[0], {0: 1, 1: 2})

    def test_bias_guard_withholds_swapped_tracks_beyond_the_matching_gate(self):
        detections = [detection(-70), detection(70, 1)]
        ais = {1: estimate(90), 2: estimate(-90)}
        self.assertEqual(self.fusion.match_with_reasons(detections, ais), ({}, {}, ['ambiguous', 'ambiguous']))
        cfg = RunConfig()
        cfg.fusion.systematic_bias_guard_m = 0.
        self.assertEqual(SARAISFusion(cfg).match(detections, ais)[0], {0: 2, 1: 1})

    def test_bias_guard_does_not_expand_match_radius(self):
        self.assertEqual(self.fusion.match_with_reasons([detection(160)], {1: estimate()})[2], ['out_of_range'])

    def test_stale_closest_proposal_cannot_be_replaced_by_fresh_neighbor(self):
        tracks = {11: estimate(0,gap=181), 22: estimate(80)}
        self.assertEqual(self.fusion.match_with_reasons([detection()], tracks), ({},{},['stale_ais']))
        previous = RunConfig()
        previous.fusion.preserve_proposed_pair = False
        self.assertEqual(SARAISFusion(previous).match([detection()],tracks)[0], {0:22})

    def test_greedy_fallback_honors_gate(self):
        with patch('sonarnet.fusion.matching._HAS_SCIPY', False):
            self.assertEqual(self.fusion.match([detection()], {1: estimate(gap=1000)})[0], {})

    def test_noisy_track_inflates_uncertainty(self):
        records = [{'timestamp': t, 'lat': 0., 'lon': x/111195.} for t, x in zip([-20, -10, 0, 10, 20], [-400, 400, -400, 400, -400])]
        est = ConstantVelocityKalman(process_noise=.01).smooth_to_time(records, 0.)
        self.assertGreater(est.position_sigma_m, 150.)
        self.assertEqual(self.fusion.match_with_reasons([detection()], {1: est})[2], ['uncertain_position'])

    def test_linear_baseline_has_finite_uncertainty(self):
        est = linear_interpolate_to_time([{'timestamp': -10, 'lat': 0., 'lon': 0.}, {'timestamp': 10, 'lat': 0., 'lon': 0.}], 0.)
        self.assertTrue(np.isfinite(est.position_sigma_m))


if __name__ == '__main__':
    unittest.main()
