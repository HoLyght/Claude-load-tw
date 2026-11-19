import json
import tempfile
import unittest
from pathlib import Path

from start import make_config, matched_nodes, prepare_provider


class ProxyConfigTests(unittest.TestCase):
    def test_fallback(self):
        config = make_config(None, "test", file_provider=True)
        group, = config["proxy-groups"]
        self.assertNotIn("proxies", group)
        self.assertEqual(group["type"], "fallback")
        self.assertEqual(group["use"], ["airport"])
        health = {"url": "https://www.cloudflare.com/cdn-cgi/trace",
                  "interval": 120, "timeout": 5000, "lazy": False}
        self.assertEqual({k: group[k] for k in health}, health)
        self.assertEqual(config["proxy-providers"]["airport"]["health-check"], {"enable": True, **health})

    def test_snapshot_dns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            snapshot = root / "snapshot.json"
            snapshot.write_text(json.dumps({"proxies": [{"name": "TW07"}],
                                            "dns": {"listen": ":53", "enable": True}}))
            self.assertEqual(prepare_provider(root, snapshot, root / "unused"), (None, True, {"enable": True}))

    def test_candidates(self):
        for nodes in ([], ["TW07"], ["TW07", "TW08", "TW09"]):
            with self.subTest(nodes=nodes):
                group = {"all": ["REJECT", "DIRECT", "COMPATIBLE", *nodes]}
                self.assertEqual(matched_nodes(group), set(nodes))
