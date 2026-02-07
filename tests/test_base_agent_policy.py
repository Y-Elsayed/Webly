from webcreeper.creeper_core.base_agent import BaseAgent


class DummyAgent(BaseAgent):
    def crawl(self):
        raise NotImplementedError

    def process_data(self, data):
        raise NotImplementedError


def test_domain_allowlist_exact():
    agent = DummyAgent(settings={"allowed_domains": ["example.com"], "allow_subdomains": False})
    assert agent.should_visit("https://example.com/a") is True
    assert agent.should_visit("https://sub.example.com/a") is False


def test_domain_allowlist_subdomains():
    agent = DummyAgent(settings={"allowed_domains": ["example.com"], "allow_subdomains": True})
    assert agent.should_visit("https://example.com/a") is True
    assert agent.should_visit("https://sub.example.com/a") is True


def test_blocked_domains_win():
    agent = DummyAgent(
        settings={
            "allowed_domains": ["example.com"],
            "blocked_domains": ["example.com"],
            "allow_subdomains": True,
        }
    )
    assert agent.should_visit("https://example.com/a") is False
    assert agent.should_visit("https://sub.example.com/a") is False


def test_allow_block_patterns():
    agent = DummyAgent(
        settings={
            "respect_robots": False,
            "allow_url_patterns": [r"/docs/"],
            "block_url_patterns": [r"/docs/private/"],
        }
    )
    assert agent.should_visit("https://example.com/docs/intro") is True
    assert agent.should_visit("https://example.com/docs/private/secret") is False
