from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from lotto_data import pipeline as p


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.now = date(2026, 11, 20)
        self.round = 1119
        self.draw_date = '2024-05-11'
        self.item = {
            'ltEpsd': self.round, 'ltRflYmd': '20240511',
            **{f'tm{i}WnNo': n for i, n in enumerate([1, 9, 12, 13, 20, 45], 1)},
            'bnsWnNo': 3,
        }
        self.record = p.normalize_official(self.item, published_at='2024-05-11T21:35:00+09:00', today=self.now)

    def test_valid_record(self):
        self.assertEqual(self.record['round'], 1119)
        self.assertTrue(self.record['verified'])

    def test_calendar_math(self):
        self.assertEqual(p.FIRST_DRAW + timedelta(days=1118 * 7), date(2024, 5, 11))

    def test_missing_official_field(self):
        bad = dict(self.item); del bad['tm6WnNo']
        with self.assertRaises(p.PipelineError): p.normalize_official(bad, today=self.now)

    def test_wrong_date(self):
        bad = dict(self.item, ltRflYmd='20240512')
        with self.assertRaises(p.PipelineError): p.normalize_official(bad, today=self.now)

    def test_future_round(self):
        with self.assertRaises(p.PipelineError): p.validate_round(self.record, today=date(2024, 5, 10))

    def test_bool_number_rejected(self):
        bad = dict(self.record, numbers=[True, 9, 12, 13, 20, 45])
        with self.assertRaises(p.PipelineError): p.validate_round(bad, today=self.now)

    def test_duplicate_main(self):
        bad = dict(self.record, numbers=[1, 9, 12, 13, 20, 20])
        with self.assertRaises(p.PipelineError): p.validate_round(bad, today=self.now)

    def test_unsorted_main(self):
        bad = dict(self.record, numbers=[9, 1, 12, 13, 20, 45])
        with self.assertRaises(p.PipelineError): p.validate_round(bad, today=self.now)

    def test_out_of_range_number(self):
        bad = dict(self.record, numbers=[0, 9, 12, 13, 20, 45])
        with self.assertRaises(p.PipelineError): p.validate_round(bad, today=self.now)

    def test_bonus_conflict(self):
        bad = dict(self.record, bonus=1)
        with self.assertRaises(p.PipelineError): p.validate_round(bad, today=self.now)

    def test_unverified_rejected(self):
        bad = dict(self.record, verified=False)
        with self.assertRaises(p.PipelineError): p.validate_round(bad, today=self.now)

    def test_timezone_required(self):
        bad = dict(self.record, published_at='2024-05-11T21:35:00')
        with self.assertRaises(p.PipelineError): p.validate_round(bad, today=self.now)

    def test_extra_schema_field(self):
        bad = dict(self.record, secret='unwanted')
        with self.assertRaises(p.PipelineError): p.validate_round(bad, today=self.now)

    def test_empty_latest(self):
        with self.assertRaises(p.PipelineError): p.extract_items({'data': {'list': []}})

    def test_official_consensus(self):
        def fetch(url):
            return {'data': {'list': [self.item]}}
        self.assertEqual(p.official_consensus(fetch=fetch, today=self.now)['round'], 1119)

    def test_official_conflict_rejected(self):
        def fetch(url):
            mismatch = dict(self.item, bnsWnNo=2)
            return {'data': {'list': [self.item if url == p.LATEST_URL else mismatch]}}
        with self.assertRaises(p.PipelineError): p.official_consensus(fetch=fetch, today=self.now)

    def test_history_round_not_found(self):
        def fetch(url):
            return {'data': {'list': [self.item if url == p.LATEST_URL else dict(self.item, ltEpsd=1120)]}}
        with self.assertRaises(p.PipelineError): p.official_consensus(fetch=fetch, today=self.now)

    def test_history_duplicate_round_rejected(self):
        def fetch(url):
            return {'data': {'list': [self.item] if url == p.LATEST_URL else [self.item, self.item]}}
        with self.assertRaises(p.PipelineError): p.official_consensus(fetch=fetch, today=self.now)

    def test_publish_then_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(p.publish(self.record, root, today=self.now), 'PUBLISHED')
            original = (root / 'latest.json').read_bytes()
            self.assertEqual(p.publish(dict(self.record, published_at='2024-05-12T12:00:00+09:00'), root, today=self.now), 'UNCHANGED')
            self.assertEqual((root / 'latest.json').read_bytes(), original)
            self.assertEqual((root / 'rounds/1119.json').read_bytes(), original)

    def test_dry_run_no_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(p.publish(self.record, root, today=self.now, dry_run=True), 'WOULD_PUBLISH')
            self.assertFalse((root / 'latest.json').exists())

    def test_regression_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p.publish(self.record, root, today=self.now)
            older = dict(self.record, round=1118, draw_date='2024-05-04')
            with self.assertRaises(p.PipelineError): p.publish(older, root, today=self.now)

    def test_nonconsecutive_gap_is_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p.publish(self.record, root, today=self.now)
            newer = dict(self.record, round=1121, draw_date='2024-05-25')
            with self.assertRaises(p.PipelineError): p.publish(newer, root, today=self.now)

    def test_existing_conflict_is_blocked_without_overwriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p.publish(self.record, root, today=self.now)
            original = (root / 'latest.json').read_bytes()
            alternate = dict(self.record, bonus=2)
            with self.assertRaises(p.PipelineError): p.publish(alternate, root, today=self.now)
            self.assertEqual((root / 'latest.json').read_bytes(), original)

    def test_corrupt_existing_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'latest.json').write_text('{not-json', encoding='utf-8')
            with self.assertRaises(p.PipelineError): p.publish(self.record, root, today=self.now)
            self.assertEqual((root / 'latest.json').read_text(encoding='utf-8'), '{not-json')

    def test_missing_round_archive_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            p.publish(self.record, root, today=self.now)
            (root / 'rounds/1119.json').unlink()
            with self.assertRaises(p.PipelineError): p.publish(self.record, root, today=self.now)

    def test_bad_schema_not_published(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bad = dict(self.record, bonus=1)
            with self.assertRaises(p.PipelineError): p.publish(bad, root, today=self.now)
            self.assertFalse((root / 'latest.json').exists())


if __name__ == '__main__':
    unittest.main()
