"""The interest profile, against a temp state/ — never the real one."""
import json
import os
import tempfile
import unittest
from unittest import mock

from eliciterlib import config, interests, rank


class TestProfile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.object(config, "out_dir", lambda name: self.tmp.name)
        p.start()
        self.addCleanup(p.stop)
        # Stale lines in a user's .env must not leak in: these are not settings any more.
        env = mock.patch.dict(os.environ, {"ELICITER_INTERESTS": "from env",
                                           "ELICITER_EXCLUDE": "env noise"})
        env.start()
        self.addCleanup(env.stop)

    def seed(self):
        interests.init(["basal cognition", "Agency", "agency ", "morphogenesis"],
                       ["benchmark", "llm"], ["cs.AI", "q-bio.NC"], now="2026-11-01T00:00:00Z")

    def propose(self, data):
        with open(interests.draft_path(), "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    # -- where config reads from ---------------------------------------------------
    def test_config_uses_built_in_defaults_without_a_profile_and_ignores_env(self):
        self.assertEqual(config.interests(), config.DEFAULT_INTERESTS)
        self.assertEqual(config.exclude(), config.DEFAULT_EXCLUDE)
        self.assertEqual(config.categories(), config.DEFAULT_CATEGORIES)

    def test_config_reads_the_profile_once_seeded(self):
        self.seed()
        self.assertEqual(config.interests(), ["basal cognition", "Agency", "morphogenesis"])
        self.assertEqual(config.exclude(), ["benchmark", "llm"])
        self.assertEqual(config.categories(), ["cs.AI", "q-bio.NC"])

    def test_profile_without_categories_gets_the_default(self):
        self.seed()
        prof = interests._read_json(interests.path())
        del prof["categories"]
        interests._write_json(interests.path(), prof)
        self.assertEqual(config.categories(), config.DEFAULT_CATEGORIES)

    def test_init_refuses_to_overwrite(self):
        self.seed()
        with self.assertRaises(SystemExit):
            self.seed()

    def test_seeding_is_not_a_tuning(self):
        self.seed()
        self.assertEqual(interests.last_tuned(interests.load()), "")

    # -- checking a proposal ---------------------------------------------------------
    def check(self, data):
        self.seed()
        return interests.check(data, interests.load())

    def test_every_change_needs_a_why(self):
        with self.assertRaisesRegex(interests.InvalidProposal, "why"):
            self.check({"interests": {"add": [{"term": "autopoiesis"}]}})

    def test_add_already_present_is_refused_case_insensitively(self):
        with self.assertRaisesRegex(interests.InvalidProposal, "already"):
            self.check({"interests": {"add": [{"term": "AGENCY", "why": "x"}]}})

    def test_drop_must_exist(self):
        with self.assertRaisesRegex(interests.InvalidProposal, "nothing to drop"):
            self.check({"exclude": {"drop": [{"term": "malware", "why": "x"}]}})

    def test_term_cannot_be_both_interest_and_exclude(self):
        with self.assertRaisesRegex(interests.InvalidProposal, "both"):
            self.check({"interests": {"add": [{"term": "llm", "why": "x"}]}})

    def test_moving_a_term_across_lists_is_allowed(self):
        got = self.check({"exclude": {"drop": [{"term": "llm", "why": "x"}]},
                          "interests": {"add": [{"term": "llm", "why": "y"}]}})
        self.assertEqual(got["interests"]["add"][0]["term"], "llm")

    def test_commas_and_empty_proposals_are_refused(self):
        with self.assertRaisesRegex(interests.InvalidProposal, "comma"):
            self.check({"interests": {"add": [{"term": "a, b", "why": "x"}]}})
        with self.assertRaisesRegex(interests.InvalidProposal, "changes nothing"):
            interests.check({}, interests.load())

    def test_cannot_drop_every_interest(self):
        drop = [{"term": t, "why": "x"} for t in ("basal cognition", "agency", "morphogenesis")]
        with self.assertRaisesRegex(interests.InvalidProposal, "no interests"):
            self.check({"interests": {"drop": drop}})

    # -- applying it -------------------------------------------------------------------
    def test_apply_updates_lists_records_history_and_removes_draft(self):
        self.seed()
        self.propose({"note": "first pass",
                      "interests": {"add": [{"term": "autopoiesis", "why": "read 3 on it"}],
                                    "drop": [{"term": "agency", "why": "too broad"}]},
                      "exclude": {"add": [{"term": "red-teaming", "why": "4 rejections"}]}})
        interests.apply(now="2026-11-24T00:00:00Z")
        prof = interests.load()
        self.assertEqual(prof["interests"], ["basal cognition", "morphogenesis", "autopoiesis"])
        self.assertEqual(prof["exclude"], ["benchmark", "llm", "red-teaming"])
        self.assertEqual(prof["history"][-1]["note"], "first pass")
        self.assertEqual(prof["history"][-1]["interests"]["drop"][0]["why"], "too broad")
        self.assertEqual(interests.last_tuned(prof), "2026-11-24T00:00:00Z")
        self.assertFalse(os.path.exists(interests.draft_path()))

    def test_invalid_proposal_leaves_profile_and_draft_alone(self):
        self.seed()
        before = interests.load()
        self.propose({"interests": {"add": [{"term": "agency", "why": "x"}]}})
        with self.assertRaises(interests.InvalidProposal):
            interests.apply()
        self.assertEqual(interests.load(), before)
        self.assertTrue(os.path.exists(interests.draft_path()))

    def test_profile_hits_match_like_the_ranker(self):
        got = interests._hits("Basal cognition in LLM agents, up to a causal prefactor",
                              {"interests": ["basal cognition", "causal order", "agency"],
                               "exclude": ["llm", "refactor"]})
        # Whole words only — `refactor` is not in `prefactor` — and half a phrase is not
        # the phrase.
        self.assertEqual(got, {"interests": ["basal cognition"], "exclude": ["llm"]})

    # -- categories ---------------------------------------------------------------------
    def test_categories_can_be_added_and_dropped(self):
        self.seed()
        self.propose({"categories": {"add": [{"term": "quant-ph", "why": "3 read by search"}],
                                     "drop": [{"term": "cs.ai", "why": "nothing read"}]}})
        interests.apply()
        self.assertEqual(config.categories(), ["q-bio.NC", "quant-ph"])

    def test_malformed_category_is_refused(self):
        with self.assertRaisesRegex(interests.InvalidProposal, "arxiv category"):
            self.check({"categories": {"add": [{"term": "quantum physics", "why": "x"}]}})

    def test_cannot_drop_every_category(self):
        drop = [{"term": c, "why": "x"} for c in ("cs.AI", "q-bio.NC")]
        with self.assertRaisesRegex(interests.InvalidProposal, "no categories"):
            self.check({"categories": {"drop": drop}})


class TestPhraseRanking(unittest.TestCase):
    def test_a_stated_phrase_needs_its_words_together(self):
        prof = rank.profile(interests=["active inference"])
        self.assertGreater(rank.score("Active inference in cells.", prof)[0], 0)
        self.assertEqual(rank.score("Fast inference for active learning.", prof)[0], 0.0)

    def test_stopwords_inside_a_phrase_are_skipped(self):
        prof = rank.profile(interests=["philosophy of time"])
        self.assertEqual(rank.score("On the philosophy of time.", prof)[1], ["philosophy time"])
        self.assertEqual(rank.score("Time series and philosophy.", prof)[0], 0.0)

    def test_an_excluded_phrase_spares_its_words_alone(self):
        prof = rank.profile(interests=["agency"], exclude=["code generation"])
        spared, _ = rank.overlap("Agency and the generation of form.", prof)
        sunk, _ = rank.overlap("Agency through code generation.", prof)
        self.assertGreater(spared, sunk)

    def test_corpus_words_stay_single_words(self):
        prof = rank.profile(notes=[{"title": "morphogenetic fields", "body": ""}],
                            interests=["basal cognition"])
        self.assertIn("morphogenetic", prof.weights)
        self.assertNotIn("morphogenetic fields", prof.weights)


if __name__ == "__main__":
    unittest.main()
