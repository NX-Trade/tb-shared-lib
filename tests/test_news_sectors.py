"""Tagging news with the sectors it is about."""

import pytest

from tb_utils import news_sectors as ns


class TestKeywords:
    @pytest.mark.parametrize(
        ("text", "sector"),
        [
            ("Pharma stocks rally after USFDA clears plant", "CNXPHRM"),
            ("Steel prices fall as China demand weakens", "CNXMET"),
            ("Crude oil jumps on supply fears", "NIFTYOIL"),
            ("PSU banks lead gains as credit growth picks up", "CNXPSBK"),
            ("Private sector banks report strong NIMs", "NIFTYPVTBA"),
            ("Cement makers hike prices", "CNXCEM"),
            ("Two-wheeler sales hit a festive high", "CNXAUTO"),
            ("IT services firms see weak deal wins", "NIFTYIT"),
            ("Real estate sales surge in top cities", "CNXREAL"),
            ("FMCG volumes recover in rural India", "CNXFMCG"),
            ("NBFCs see stress in microfinance", "NSEFIN"),
            ("Hospitals expand capacity in tier-2 cities", "NIFTYHEAL"),
            ("Multiplex chains eye a strong box office quarter", "NIFTYMEDIA"),
        ],
    )
    def test_a_sector_word_tags_its_sector(self, text, sector):
        assert sector in ns.keyword_sectors(text)

    @pytest.mark.parametrize(
        "text",
        [
            "Central bank signals a pause in rate hikes",
            "World Bank cuts India growth forecast",
            "Reserve Bank of Australia holds rates",
            "Sensex ends flat as investors await earnings",
            "Fed minutes due this week",
            "",
        ],
    )
    def test_a_phrase_that_only_contains_a_sector_word_does_not(self, text):
        assert "BANKNIFTY" not in ns.keyword_sectors(text)

    def test_a_story_can_belong_to_two_sectors(self):
        assert ns.keyword_sectors("Steel and cement stocks gain on infra push") >= {
            "CNXMET",
            "CNXCEM",
        }

    def test_a_word_inside_another_word_does_not_count(self):
        assert (
            ns.keyword_sectors("The ottoman empire museum reopened") == set()
        )  # "ott" is not "ottoman"
        assert "CNXPHRM" not in ns.keyword_sectors("pharmacy chain expands")


class TestStocks:
    def sectors(self):
        constituents = [
            ("Nifty Bank", "HDFCBANK"),
            ("Nifty Private Bank", "HDFCBANK"),
            ("Nifty IT", "TCS"),
            ("Nifty Oil and Gas", "RELIANCE"),
        ]
        labels = [
            ("HDFCBANK", "Financial Services"),
            ("ACC", "Construction Materials"),
            ("XYZ", "Textiles"),
        ]
        return ns.build_symbol_sectors(constituents, labels)

    def test_a_stock_is_in_every_sector_index_that_lists_it_and_its_labelled_sector(self):
        assert self.sectors()["HDFCBANK"] == {"BANKNIFTY", "NIFTYPVTBA", "NSEFIN"}

    def test_a_label_covers_a_sector_whose_constituent_list_nse_does_not_publish(self):
        assert self.sectors()["ACC"] == {"CNXCEM"}  # no Nifty Cement list

    def test_a_label_with_no_index_gives_no_sector(self):
        assert "XYZ" not in self.sectors()

    def test_index_names_match_across_nses_two_spellings(self):
        assert ns.normalise_index_name("Nifty Oil & Gas") == ns.normalise_index_name(
            "NIFTY OIL AND GAS"
        )
        assert ns.normalise_index_name("NIFTY HEALTHCARE INDEX") == ns.normalise_index_name(
            "Nifty Healthcare"
        )


class TestTagging:
    def sectors(self):
        return {"TCS": {"NIFTYIT"}, "HDFCBANK": {"BANKNIFTY", "NSEFIN"}}

    def test_stocks_and_words_both_contribute_and_the_result_is_sorted(self):
        out = ns.tag_sectors("TCS wins a deal as crude slides", None, "TCS", self.sectors())
        assert out == "NIFTYIT,NIFTYOIL"

    def test_a_story_about_no_sector_is_none(self):
        assert (
            ns.tag_sectors("Sensex ends flat", "Markets await the Fed", None, self.sectors())
            is None
        )
        assert ns.tag_sectors("Sensex ends flat", None, "UNKNOWN", self.sectors()) is None

    def test_symbols_are_read_whatever_their_case_and_spacing(self):
        assert (
            ns.tag_sectors("Results day", None, " tcs , hdfcbank", self.sectors())
            == "BANKNIFTY,NIFTYIT,NSEFIN"
        )

    def test_the_summary_is_read_too(self):
        assert ns.tag_sectors("Results", "Pharma exports up", None, {}) == "CNXPHRM"

    def test_the_result_always_fits_the_column(self):
        everything = " ".join(w for s in ns.SECTORS for w in s.keywords[:1])
        out = ns.tag_sectors(everything, None, None, {})
        assert out is not None and len(out) <= ns.SECTOR_MAX_LEN

    def test_every_sector_symbol_is_unique(self):
        symbols = [s.symbol for s in ns.SECTORS]
        assert len(symbols) == len(set(symbols))
