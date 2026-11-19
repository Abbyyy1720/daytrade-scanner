import unittest
from unittest.mock import patch

import pandas as pd

from fetch_data import fetch_batch_history, valid_history, cutoff_history, latest_completed_market_date


def history():
    return pd.DataFrame(
        {"Open": 100., "High": 102., "Low": 99., "Close": 101., "Volume": 1000.},
        index=pd.date_range("2026-09-01", periods=30),
    )


class HistoryTests(unittest.TestCase):
    def test_shared_index_padding_does_not_discard_valid_ticker(self):
        original = history()
        padded = original.reindex(pd.date_range("2026-08-30", periods=34))
        pd.testing.assert_frame_equal(valid_history(padded), original, check_freq=False)

    def test_partial_latest_bar_still_rejected(self):
        frame = history()
        frame.loc[frame.index[-1], "Close"] = float("nan")
        self.assertIsNone(valid_history(frame))

    def test_zero_and_infinite_latest_price_still_rejected(self):
        for bad in (0., float("inf"), -1.):
            with self.subTest(price=bad):
                frame = history()
                frame.loc[frame.index[-1], "Close"] = bad
                self.assertIsNone(valid_history(frame))


    def test_zero_volume_alignment_padding_is_ignored(self):
        original = history()
        padded = original.reindex(pd.date_range("2026-09-01", periods=31))
        padded.loc[padded.index[-1], "Volume"] = 0.0
        pd.testing.assert_frame_equal(valid_history(padded), original, check_freq=False)

    def test_missing_price_with_real_volume_is_rejected(self):
        frame = history()
        frame.loc[frame.index[-1], ["Open", "High", "Low", "Close"]] = float("nan")
        frame.loc[frame.index[-1], "Volume"] = 1234.
        self.assertIsNone(valid_history(frame))

    def test_market_cutoff_before_5pm_taiwan(self):
        from datetime import datetime, timezone, timedelta
        taipei = timezone(timedelta(hours=8))
        self.assertEqual(latest_completed_market_date(datetime(2026, 11, 19, 2, 10, tzinfo=taipei)).isoformat(), "2026-11-18")
        self.assertEqual(latest_completed_market_date(datetime(2026, 11, 19, 17, 17, tzinfo=taipei)).isoformat(), "2026-11-19")
        self.assertEqual(latest_completed_market_date(datetime(2026, 11, 23, 2, 10, tzinfo=taipei)).isoformat(), "2026-11-20")

    def test_future_partial_candle_is_dropped_before_validation(self):
        original = history()
        padded = original.reindex(pd.date_range("2026-09-01", periods=31))
        padded.loc[padded.index[-1], "Volume"] = 1000.
        self.assertIsNone(valid_history(padded))
        cleaned = cutoff_history(padded, original.index[-1].date())
        pd.testing.assert_frame_equal(valid_history(cleaned), original, check_freq=False)

    def test_current_invalid_candle_is_not_silently_dropped(self):
        original = history()
        original.loc[original.index[-1], "Close"] = float("nan")
        cleaned = cutoff_history(original, original.index[-1].date())
        self.assertIsNone(valid_history(cleaned))

    def test_empty_and_short_history_rejected(self):
        self.assertIsNone(valid_history(history().iloc[:19]))
        self.assertIsNone(valid_history(history() * float("nan")))

    @patch("fetch_data.time.sleep")
    @patch("fetch_data.yf.download")
    def test_single_ticker_multiindex_is_unpacked(self, download, sleep):
        download.return_value = pd.concat({"2330.TW": history()}, axis=1)
        result = fetch_batch_history({"2330.TW": None})
        self.assertEqual(list(result), ["2330.TW"])
        self.assertEqual(download.call_count, 1)

    @patch("fetch_data.time.sleep")
    @patch("fetch_data.yf.download")
    def test_only_invalid_ticker_is_retried(self, download, sleep):
        good = history()
        bad = history()
        bad.loc[bad.index[-1], "Close"] = 0.
        download.side_effect = [pd.concat({"2330.TW": good, "1101.TW": bad}, axis=1),
                                pd.concat({"1101.TW": good}, axis=1)]
        result = fetch_batch_history({"2330.TW": None, "1101.TW": None})
        self.assertEqual(set(result), {"2330.TW", "1101.TW"})
        self.assertEqual(download.call_args_list[1].kwargs["tickers"], ["1101.TW"])


if __name__ == "__main__":
    unittest.main()
