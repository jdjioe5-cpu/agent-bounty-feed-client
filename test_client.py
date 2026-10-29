#!/usr/bin/env python3
"""Unit and integration tests for AgentBountyFeedClient."""
import unittest
from client import AgentBountyFeedClient, format_table


class TestAgentBountyFeedClient(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = AgentBountyFeedClient(timeout=20, retries=3)

    def test_01_initialize(self):
        res = self.client.initialize()
        self.assertIn("protocolVersion", res)
        self.assertIn("serverInfo", res)

    def test_02_list_tools(self):
        tools = self.client.list_tools()
        self.assertIsInstance(tools, list)
        tool_names = [t.get("name") for t in tools]
        self.assertIn("list_bounties", tool_names)

    def test_03_list_bounties(self):
        bounties = self.client.list_bounties(limit=3, exclude_requires="kyc,stake,bond")
        self.assertIsInstance(bounties, list)
        if bounties:
            b = bounties[0]
            self.assertIn("id", b)
            self.assertIn("title", b)
            self.assertIn("url", b)

    def test_04_format_table(self):
        sample = [{
            "est_usd": 10,
            "source": "test_src",
            "requires": ["wallet_evm"],
            "title": "Test Bounty Task",
            "url": "https://example.com/bounty/1"
        }]
        table = format_table(sample)
        self.assertIn("test_src", table)
        self.assertIn("Test Bounty Task", table)


if __name__ == "__main__":
    unittest.main()
